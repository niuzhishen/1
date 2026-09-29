"""调用 OpenAI 兼容接口生成群聊摘要。"""

from __future__ import annotations

import logging
import time
from datetime import datetime

from openai import OpenAI

from .config import config

logger = logging.getLogger("qq_summarizer")

def build_system_prompt(focus: str) -> str:
    """生成给大模型的系统提示词；focus 为机器人主人关注的核心话题。"""
    focus_block = ""
    if focus.strip():
        focus_block = f"""
## 🎯 重点关注速览
主人最关心以下话题，请优先、详细地提取（宁多勿漏，逐条列出关键信息点，
包含具体名称、数字、时间等细节）：
{focus.strip()}
若这段时间内没有相关讨论，写「这段时间没有相关讨论」。

"""
    return f"""你是一名群聊内容分析助手。请根据提供的 QQ 群聊记录，生成一份简明、结构化的中文摘要，让没看群的人能快速了解发生了什么。

请按以下 Markdown 结构输出（没有内容的章节可以省略）：

# 📋 群聊摘要
{focus_block}
## 主要话题
按讨论热度列出 3~6 个话题，每个话题用 1~3 句话概括大家聊了什么。

## 结论与决定
群里达成的共识、做出的决定、安排的任务。

## 待跟进的问题
还没有结果、需要后续处理或回应的事项。

## 值得注意的信息
重要的链接、时间、地点、通知、资源分享等。

规则：
1. 只依据给出的聊天记录总结，绝不编造内容或人名。
2. 如果大部分是无意义闲聊，也要如实概括整体氛围和梗。
3. 保持客观中立，不要评价群成员。
4. 除「重点关注速览」外，其余部分总长度控制在 600 字以内。"""


class LLMError(Exception):
    pass


def build_transcript(messages: list[dict]) -> str:
    """把消息列表转成喂给模型的聊天记录文本。"""
    lines = []
    for msg in messages:
        when = datetime.fromtimestamp(msg["ts"]).strftime("%m-%d %H:%M")
        name = msg.get("nickname") or f"用户{msg.get('user_id', '?')}"
        content = (msg.get("content") or "").strip()
        if not content:
            continue
        max_chars = config.llm_max_chars_per_message
        if len(content) > max_chars:
            content = content[:max_chars] + "…(截断)"
        lines.append(f"[{when}] {name}: {content}")
    return "\n".join(lines)


def summarize_messages(
    messages: list[dict],
    group_name: str = "",
    time_range: str = "",
) -> str:
    """调用大模型总结消息列表，返回 Markdown 摘要。"""
    if not config.llm_api_key:
        raise LLMError("还没有配置 LLM_API_KEY，请先在 .env 中填写大模型 API Key。")
    if not messages:
        raise LLMError("该时间段内没有收集到任何消息，无法总结。")

    # 只取最近的 N 条，防止超出上下文
    if len(messages) > config.llm_max_messages:
        messages = messages[-config.llm_max_messages :]

    transcript = build_transcript(messages)
    title = group_name or "群聊"
    user_prompt = (
        f"以下是 QQ 群「{title}」"
        + (f"在 {time_range} 期间" if time_range else "")
        + f"的聊天记录，共 {len(messages)} 条：\n\n"
        + transcript
    )

    client = OpenAI(api_key=config.llm_api_key, base_url=config.llm_base_url or None)

    last_error: Exception | None = None
    for attempt in range(3):
        try:
            resp = client.chat.completions.create(
                model=config.llm_model,
                messages=[
                    {"role": "system", "content": build_system_prompt(config.summary_focus)},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.3,
            )
            content = (resp.choices[0].message.content or "").strip()
            if not content:
                raise LLMError("模型返回了空内容，请重试。")
            return content
        except Exception as e:  # noqa: BLE001
            last_error = e
            logger.warning("摘要生成失败（第 %d 次）：%s", attempt + 1, e)
            if attempt < 2:
                time.sleep(2**attempt)
    raise LLMError(f"摘要生成失败：{last_error}")
