"""端到端集成测试：

- 启动一个模拟 NapCat 的 OneBot v11 WebSocket 服务器
- 启动一个模拟大模型的 OpenAI 兼容 HTTP 服务器
- 以子进程方式启动 bot.py，验证：
    1. 机器人能通过正向 WebSocket 连接上来
    2. 群消息被正确存入 SQLite
    3. 「总结」命令能调用大模型并回发摘要
    4. 「日报」命令能立即生成日报
"""

from __future__ import annotations

import asyncio
import json
import os
import signal
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import websockets

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TMP = os.path.join(ROOT, "data", "integration_tmp")
DB_PATH = os.path.join(TMP, "messages.db")
ONEBOT_PORT = 3101
LLM_PORT = 3102
SELF_ID = 10001
GROUP_ID = 777
OWNER_QQ = 2000  # 主人 QQ：摘要只私聊发给这个人

group_msgs: list[dict] = []    # bot 发到群里的消息（期望为 0）
private_msgs: list[dict] = []  # bot 发出的私聊消息


# ---------------------------------------------------------------------------
# 模拟大模型（OpenAI 兼容 /chat/completions）
# ---------------------------------------------------------------------------
class FakeLLM(BaseHTTPRequestHandler):
    def do_POST(self):  # noqa: N802
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length) or b"{}")
        # 断言请求结构正确
        assert body.get("model"), "LLM 请求缺少 model"
        assert body.get("messages"), "LLM 请求缺少 messages"
        resp = {
            "id": "fake",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": body["model"],
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": "这是测试摘要（来自模拟大模型）"},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        }
        data = json.dumps(resp).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):  # 静音
        pass


# ---------------------------------------------------------------------------
# 模拟 NapCat（OneBot v11 正向 WebSocket）
# ---------------------------------------------------------------------------
def group_msg(mid: int, user_id: int, nickname: str, text: str) -> dict:
    return {
        "time": int(time.time()),
        "self_id": SELF_ID,
        "post_type": "message",
        "message_type": "group",
        "sub_type": "normal",
        "message_id": mid,
        "group_id": GROUP_ID,
        "user_id": user_id,
        "anonymous": None,
        "message": [{"type": "text", "data": {"text": text}}],
        "raw_message": text,
        "font": 0,
        "sender": {
            "user_id": user_id,
            "nickname": nickname,
            "card": "",
            "sex": "unknown",
            "age": 0,
            "area": "",
            "level": "1",
            "role": "member",
            "title": "",
        },
    }


async def onebot_handler(ws):
    # 握手：lifecycle connect
    await ws.send(
        json.dumps(
            {
                "time": int(time.time()),
                "self_id": SELF_ID,
                "post_type": "meta_event",
                "meta_event_type": "lifecycle",
                "sub_type": "connect",
            }
        )
    )

    async def respond(payload: dict, data):
        await ws.send(
            json.dumps(
                {
                    "status": "ok",
                    "retcode": 0,
                    "data": data,
                    "message": "",
                    "echo": payload.get("echo"),
                }
            )
        )

    async def api_responder():
        """持续应答 bot 发来的 API 请求。"""
        try:
            async for raw in ws:
                payload = json.loads(raw)
                action = payload.get("action")
                params = payload.get("params", {})
                print(f"    [mock] 收到 API 请求: {action} echo={payload.get('echo')}")
                if action == "get_group_info":
                    await respond(
                        payload,
                        {
                            "group_id": GROUP_ID,
                            "group_name": "集成测试群",
                            "member_count": 10,
                            "max_member_count": 200,
                        },
                    )
                elif action == "send_private_msg" or params.get("message_type") == "private":
                    private_msgs.append(params)
                    await respond(payload, {"message_id": 9000 + len(private_msgs)})
                elif action in ("send_group_msg", "send_msg"):
                    group_msgs.append(params)
                    await respond(payload, {"message_id": 8000 + len(group_msgs)})
                else:
                    await respond(payload, None)
        except websockets.ConnectionClosed:
            pass

    async def scripted_events():
        """按脚本推送群消息与命令。"""
        await asyncio.sleep(1)  # 等 bot 初始化完成
        texts = [
            "今晚八点开会，讨论新版本发布",
            "收到，我会准时参加",
            "会议纪要我来写",
            "好的好的 👌",
            "散会前记得填问卷",
        ]
        for i, t in enumerate(texts):
            await ws.send(json.dumps(group_msg(i + 1, 2000 + i % 3, f"成员{i % 3}", t)))
            await asyncio.sleep(0.1)
        await asyncio.sleep(1.5)
        # 主人在群里触发「总结」
        await ws.send(json.dumps(group_msg(100, OWNER_QQ, "主人", "总结 1小时")))
        await asyncio.sleep(5)
        # 主人触发「日报」
        await ws.send(json.dumps(group_msg(101, OWNER_QQ, "主人", "日报")))
        await asyncio.sleep(5)
        # 非主人试图触发「总结」——必须被静默忽略，不能产生任何回复
        await ws.send(json.dumps(group_msg(102, 2999, "路人", "总结 1小时")))

    responder = asyncio.create_task(api_responder())
    try:
        await scripted_events()
        await asyncio.sleep(40)  # 留足时间让 bot 处理完（含非主人触发的观察期）
    finally:
        responder.cancel()


async def run_onebot_server(stop: asyncio.Event):
    async with websockets.serve(onebot_handler, "127.0.0.1", ONEBOT_PORT):
        await stop.wait()


def main():
    os.makedirs(TMP, exist_ok=True)
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)

    # 模拟大模型服务器
    llm_server = ThreadingHTTPServer(("127.0.0.1", LLM_PORT), FakeLLM)
    threading.Thread(target=llm_server.serve_forever, daemon=True).start()

    # 机器人子进程环境
    env = dict(os.environ)
    env.update(
        {
            "ENVIRONMENT": "test",
            "DRIVER": "~fastapi+~websockets",
            "HOST": "127.0.0.1",
            "PORT": "3103",
            "ONEBOT_WS_URLS": json.dumps([f"ws://127.0.0.1:{ONEBOT_PORT}"]),
            "ONEBOT_ACCESS_TOKEN": "",
            "TRACK_GROUPS": "*",
            "ON_CONNECT_GROUP_IDS": "[]",
            "LLM_API_KEY": "test-key",
            "LLM_BASE_URL": f"http://127.0.0.1:{LLM_PORT}/v1",
            "LLM_MODEL": "fake-model",
            "DIGEST_CRON_HOUR": "23",
            "DIGEST_CRON_MINUTE": "59",
            "DIGEST_LOOKBACK_HOURS": "24",
            "DB_PATH": DB_PATH,
            "COMMAND_START": json.dumps(["", "/"]),
            "OWNER_QQ": str(OWNER_QQ),
        }
    )

    stop = asyncio.Event()

    async def amain():
        server_task = asyncio.create_task(run_onebot_server(stop))
        await asyncio.sleep(0.5)

        bot_proc = subprocess.Popen(
            [sys.executable, "bot.py"],
            cwd=ROOT,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        started = time.time()
        try:
            # 等待全部流程完成（消息→总结→日报→非主人触发观察期，约 17 秒）
            while time.time() - started < 25:
                await asyncio.sleep(0.5)
                if len(private_msgs) >= 4 and time.time() - started > 22:
                    break
        finally:
            stop.set()
            bot_proc.send_signal(signal.SIGINT)
            try:
                bot_proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                bot_proc.kill()
            out = bot_proc.stdout.read().decode(errors="replace") if bot_proc.stdout else ""
            await server_task

        return out

    bot_log = asyncio.run(amain())

    # ---------------- 断言 ----------------
    import sqlite3

    failures = []

    def check(cond, desc):
        print(("  ✅ " if cond else "  ❌ ") + desc)
        if not cond:
            failures.append(desc)

    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute(
        "SELECT content, nickname FROM messages WHERE group_id = ? ORDER BY ts",
        (GROUP_ID,),
    ).fetchall()

    check(len(rows) == 5, f"数据库收到 5 条群消息（实际 {len(rows)} 条）")
    check(any("今晚八点开会" in r[0] for r in rows), "消息内容完整入库")
    check(
        not any("总结" == r[0].strip() or r[0].startswith("总结 ") for r in rows),
        "命令消息本身没有被当作聊天内容入库",
    )

    private_texts = [str(p.get("message", "")) for p in private_msgs]
    flat = " || ".join(private_texts)

    check(len(group_msgs) == 0, f"群里零输出：机器人没有向任何群发消息（实际 {len(group_msgs)} 条）")
    check(
        all(int(p.get("user_id", -1)) == OWNER_QQ for p in private_msgs) and private_msgs,
        f"所有回复都私聊发给了主人 {OWNER_QQ}",
    )
    check("正在总结" in flat, "「总结」命令私聊发送了进度提示")
    check("这是测试摘要" in flat, "「总结」命令私聊回发了大模型生成的摘要")
    check("正在生成群" in flat and "日报" in flat, "「日报」命令私聊发送了进度提示")
    check("群聊日报" in flat, "「日报」命令私聊回发了日报")
    check(
        len(private_msgs) == 4,
        f"非主人触发「总结」被静默忽略（私聊消息数 {len(private_msgs)}，期望恰好 4 条）",
    )

    if failures:
        print("\n----- 机器人日志（末尾 40 行）-----")
        print("\n".join(bot_log.splitlines()[-40:]))
        print("\n----- bot 发出的私聊消息 -----")
        for m in private_texts:
            print(repr(m)[:200])
        print("\n----- bot 发出的群消息 -----")
        for m in group_msgs:
            print(repr(m)[:200])
        sys.exit(1)

    print("\n🎉 集成测试全部通过：消息入库正常，摘要只私聊发给主人，群内零输出，非主人触发被忽略。")


if __name__ == "__main__":
    main()
