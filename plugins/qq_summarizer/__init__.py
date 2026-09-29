"""QQ 群聊消息收集 + 大模型摘要机器人。

- 通过 OneBot 11（NapCat 正向 WebSocket）接收群消息并存入 SQLite
- 每天定时生成「群聊日报」，通过私聊只发给机器人主人（OWNER_QQ）
- 主人在群里发送 总结 /总结 命令可手动总结，结果同样私聊发送
- 群里其他人无法触发命令、看不到任何输出
- 可选：机器人上线后自动对指定群开启全体禁言（防止群成员消息打扰，仅用于「只读旁观」场景）
"""

from __future__ import annotations

import logging
import time
from datetime import datetime

import anyio
import nonebot
import nonebot.adapters.onebot.v11 as onebot
from nonebot import get_driver, get_bots, on_command, on_message, require
from nonebot.adapters.onebot.v11 import Bot, Message, MessageEvent
from nonebot.adapters.onebot.v11.event import GroupMessageEvent
from nonebot.exception import FinishedException
from nonebot.params import CommandArg

require("nonebot_plugin_apscheduler")
from nonebot_plugin_apscheduler import scheduler

from .config import config
from .db import MessageStore
from .summarizer import LLMError, summarize_messages
from .timeutil import format_time_range, parse_last_n, parse_window

logger = logging.getLogger("qq_summarizer")

driver = get_driver()
store = MessageStore(config.db_path)

# ---------------------------------------------------------------------------
# OneBot 连接：适配器读取 ONEBOT_WS_URLS 配置，自动以 WebSocket 客户端身份
# 连接 NapCat（正向 WebSocket），无需手动 setup
# ---------------------------------------------------------------------------
if "OneBot V11" not in nonebot.get_adapters():
    driver.register_adapter(onebot.Adapter)

MUTE_NOTICE = (
    "🤖 群聊总结机器人已上线。\n"
    "本群已被设置为全体禁言：机器人会静默记录群消息，"
    "并定时向管理员私聊发送群聊日报。如需恢复发言，请管理员关闭全体禁言。"
)

_seen_groups: set[int] = set()


# ---------------------------------------------------------------------------
# 主人私聊通道：所有摘要/日报结果只私聊发给 OWNER_QQ，群里不可见
# ---------------------------------------------------------------------------
def is_owner(event: MessageEvent) -> bool:
    return config.owner_qq is not None and event.user_id == config.owner_qq


async def send_to_owner(bot: Bot, text: str) -> None:
    if config.owner_qq is None:
        logger.warning("未配置 OWNER_QQ，无法私聊发送结果。请在 .env 中设置 OWNER_QQ。")
        return
    await bot.send_private_msg(user_id=config.owner_qq, message=text)


@driver.on_bot_connect
async def on_bot_connect(bot: Bot) -> None:
    """机器人连接成功后，对配置中的群开启全体禁言并发送提示。"""
    logger.info("OneBot 已连接：%s", bot.self_id)
    for gid in config.on_connect_group_ids:
        try:
            await bot.set_group_whole_ban(group_id=gid, enable=True)
            await bot.send_group_msg(group_id=gid, message=MUTE_NOTICE)
            logger.info("已对群 %s 开启全体禁言", gid)
        except Exception as e:  # noqa: BLE001
            logger.warning("对群 %s 设置全体禁言失败：%s", gid, e)


# ---------------------------------------------------------------------------
# 群消息收集
# ---------------------------------------------------------------------------

_TYPE_PLACEHOLDER = {
    "image": "[图片]",
    "record": "[语音]",
    "video": "[视频]",
    "face": "[表情]",
    "forward": "[转发消息]",
    "reply": "[回复]",
    "json": "[卡片消息]",
    "xml": "[XML消息]",
    "poke": "[戳一戳]",
}


def extract_text(message: Message) -> str:
    """把一条消息转成纯文本。非文本内容用占位符表示。"""
    parts: list[str] = []
    for seg in message:
        t = seg.type
        if t == "text":
            parts.append(str(seg.data.get("text", "")))
        elif t == "at":
            qq = seg.data.get("qq", "")
            parts.append(f"[at:{qq}]" if qq != "all" else "[at:全体成员]")
        elif t in _TYPE_PLACEHOLDER:
            parts.append(_TYPE_PLACEHOLDER[t])
        else:
            parts.append(f"[{t}]")
    return "".join(parts).strip()


async def get_group_name(bot: Bot, group_id: int) -> str:
    cached = store.get_meta(f"group_name:{group_id}")
    if cached:
        return cached
    try:
        info = await bot.get_group_info(group_id=group_id)
        name = (info or {}).get("group_name") or ""
        if name:
            store.set_meta(f"group_name:{group_id}", name)
            return name
    except Exception as e:  # noqa: BLE001
        logger.debug("获取群 %s 信息失败：%s", group_id, e)
    return f"群{group_id}"


msg_handler = on_message(priority=10, block=False)


@msg_handler.handle()
async def collect_group_message(bot: Bot, event: MessageEvent) -> None:
    if not isinstance(event, GroupMessageEvent):
        return
    gid = event.group_id
    if not config.should_track(gid):
        return

    if gid not in _seen_groups:
        _seen_groups.add(gid)
        name = await get_group_name(bot, gid)
        logger.info("开始收集群消息：%s（%s）", gid, name)

    text = extract_text(event.message)
    if not text:
        return

    store.add_message(
        ts=event.time or time.time(),
        group_id=gid,
        user_id=event.user_id,
        nickname=event.sender.nickname or f"用户{event.user_id}",
        content=text,
        raw_type=event.sub_type or "normal",
    )


# ---------------------------------------------------------------------------
# 手动总结命令：总结 /总结 [时间窗口|条数]
#   例如：总结 2小时 / 总结 昨天 / 总结 30分钟 / 总结 100条 / 总结
# ---------------------------------------------------------------------------
_command_matchers = [
    on_command(trigger, priority=5, block=True)
    for trigger in config.command_triggers
]


async def _finish_to_owner(bot: Bot, text: str) -> None:
    """把结果私聊发给主人并结束命令处理。"""
    await send_to_owner(bot, text)
    raise FinishedException


async def handle_summary_command(
    bot: Bot, event: MessageEvent, args: Message = CommandArg()
) -> None:
    # 只响应主人；其他人触发时静默忽略，不产生任何可见输出
    if not is_owner(event):
        raise FinishedException

    if not isinstance(event, GroupMessageEvent):
        await _finish_to_owner(
            bot, "「总结」命令需要在想总结的群里发送，我会把结果私聊发给你。"
        )

    gid = event.group_id
    arg_text = args.extract_plain_text().strip()

    now = datetime.now()
    messages: list[dict] = []
    window_desc = ""

    n = parse_last_n(arg_text)
    if n:
        messages = store.fetch_last_n(gid, n)
        window_desc = f"最近 {len(messages)} 条"
    else:
        parsed = parse_window(arg_text, now=now) if arg_text else None
        if parsed is None:
            if arg_text:
                await _finish_to_owner(
                    bot,
                    f"没看懂时间参数「{arg_text}」。\n"
                    "支持：2小时 / 30分钟 / 今天 / 昨天 / 100条 / 不带参数（默认最近 "
                    f"{config.default_window_minutes} 分钟）",
                )
            start = now.timestamp() - config.default_window_minutes * 60
            end = now.timestamp()
            window_desc = f"最近 {config.default_window_minutes} 分钟"
        else:
            start, end = parsed
            window_desc = format_time_range(start, end)
        messages = store.fetch_window(gid, start, end, limit=config.llm_max_messages)

    if not messages:
        await _finish_to_owner(bot, f"该时间范围（{window_desc}）内没有收集到消息。")

    await send_to_owner(
        bot, f"⏳ 正在总结群 {gid} {window_desc} 的 {len(messages)} 条消息，请稍候…"
    )

    group_name = await get_group_name(bot, gid)
    try:
        summary = await anyio.to_thread.run_sync(
            summarize_messages, messages, group_name, window_desc
        )
    except LLMError as e:
        await _finish_to_owner(bot, f"❌ {e}")
    except Exception as e:  # noqa: BLE001
        logger.exception("生成摘要出错")
        await _finish_to_owner(bot, f"❌ 生成摘要出错：{e}")

    await _finish_to_owner(bot, f"📋 群「{group_name}」的总结：\n\n{summary}")


for _m in _command_matchers:
    _m.handle()(handle_summary_command)


# ---------------------------------------------------------------------------
# 手动日报命令：日报（立即生成最近 DIGEST_LOOKBACK_HOURS 小时的日报）
# ---------------------------------------------------------------------------
digest_cmd = on_command("日报", priority=5, block=True)


@digest_cmd.handle()
async def handle_manual_digest(
    bot: Bot, event: MessageEvent, args: Message = CommandArg()
) -> None:
    # 只响应主人；其他人触发时静默忽略
    if not is_owner(event):
        raise FinishedException

    if not isinstance(event, GroupMessageEvent):
        await _finish_to_owner(
            bot, "「日报」命令需要在想生成日报的群里发送，我会把结果私聊发给你。"
        )

    gid = event.group_id
    end = time.time()
    start = end - config.digest_lookback_hours * 3600
    messages = store.fetch_window(gid, start, end, limit=config.llm_max_messages)
    if not messages:
        await _finish_to_owner(
            bot, f"最近 {config.digest_lookback_hours:g} 小时内没有收集到消息。"
        )

    await send_to_owner(
        bot, f"⏳ 正在生成群 {gid} 的日报（{len(messages)} 条消息），请稍候…"
    )
    group_name = await get_group_name(bot, gid)
    window_desc = format_time_range(start, end)
    try:
        summary = await anyio.to_thread.run_sync(
            summarize_messages, messages, group_name, window_desc
        )
    except Exception as e:  # noqa: BLE001
        logger.exception("生成日报出错")
        await _finish_to_owner(bot, f"❌ 生成日报出错：{e}")
    date_str = datetime.now().strftime("%Y-%m-%d")
    await _finish_to_owner(bot, f"📊 群聊日报 · {date_str} · 群「{group_name}」\n\n{summary}")


# ---------------------------------------------------------------------------
# 定时日报
# ---------------------------------------------------------------------------
async def send_daily_digest() -> None:
    """定时日报：汇总各群消息，摘要通过私聊只发给主人，不会出现在任何群里。"""
    if config.owner_qq is None:
        logger.warning("未配置 OWNER_QQ，日报无法私聊发送，跳过。请在 .env 中设置。")
        return

    bots = get_bots()
    if not bots:
        logger.warning("日报时间到了，但没有可用的 OneBot 连接，跳过。")
        return
    bot: Bot = next(iter(bots.values()))  # type: ignore[assignment]

    end = time.time()
    start = end - config.digest_lookback_hours * 3600

    targets = (
        config.digest_groups
        if config.digest_groups
        else store.groups_with_messages_since(start)
    )
    if not targets:
        logger.info("日报：最近 %s 小时内没有任何群消息，跳过发送。", config.digest_lookback_hours)
        return

    date_str = datetime.now().strftime("%Y-%m-%d")
    sent = 0
    for gid in targets:
        try:
            messages = store.fetch_window(gid, start, end, limit=config.llm_max_messages)
            if not messages:
                continue
            group_name = await get_group_name(bot, gid)
            window_desc = format_time_range(start, end)
            summary = await anyio.to_thread.run_sync(
                summarize_messages, messages, group_name, window_desc
            )
            await send_to_owner(
                bot,
                f"📊 群聊日报 · {date_str} · 群「{group_name}」（{gid}）\n\n{summary}",
            )
            sent += 1
            logger.info("已私聊发送日报：群 %s（%s 条消息）", gid, len(messages))
        except Exception as e:  # noqa: BLE001
            logger.warning("生成/发送群 %s 的日报失败：%s", gid, e)
    if sent:
        logger.info("本次日报共私聊发送 %s 个群的摘要。", sent)


scheduler.add_job(
    send_daily_digest,
    "cron",
    hour=config.digest_cron_hour,
    minute=config.digest_cron_minute,
    id="qq_group_daily_digest",
    timezone=config.digest_timezone,
    misfire_grace_time=600,
)
logger.info(
    "群聊总结机器人已加载：每天 %02d:%02d 生成日报并私聊发送给 %s；数据文件 %s",
    config.digest_cron_hour,
    config.digest_cron_minute,
    f"OWNER_QQ={config.owner_qq}" if config.owner_qq else "（未配置，请先设置 OWNER_QQ）",
    config.db_path,
)
