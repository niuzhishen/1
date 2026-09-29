"""不依赖 nonebot 的核心逻辑测试：时间窗口解析 + SQLite 存储 + 转录文本。"""

import os
import sys
import tempfile
import time
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# 插件包初始化需要 nonebot 环境（这里不会真正连接任何服务）
import nonebot  # noqa: E402

nonebot.init(driver="~fastapi")

from plugins.qq_summarizer.db import MessageStore  # noqa: E402
from plugins.qq_summarizer.timeutil import (  # noqa: E402
    format_time_range,
    parse_last_n,
    parse_window,
)


def test_parse_window():
    now = datetime(2026, 9, 29, 22, 0, 0)
    now_ts = now.timestamp()

    start, end = parse_window("2小时", now)
    assert abs((end - start) - 7200) < 1
    assert abs(end - now_ts) < 1

    start, end = parse_window("30分钟", now)
    assert abs((end - start) - 1800) < 1

    start, end = parse_window("今天", now)
    assert datetime.fromtimestamp(start) == datetime(2026, 9, 29, 0, 0, 0)

    start, end = parse_window("昨天", now)
    assert datetime.fromtimestamp(start) == datetime(2026, 9, 28, 0, 0, 0)
    assert datetime.fromtimestamp(end) == datetime(2026, 9, 29, 0, 0, 0)

    start, end = parse_window("1.5h", now)
    assert abs((end - start) - 5400) < 1

    assert parse_window("随便写点啥", now) is None
    assert parse_window("", now) is None


def test_parse_last_n():
    assert parse_last_n("100条") == 100
    assert parse_last_n("最近 50 条消息") == 50
    assert parse_last_n("两小时") is None


def test_store():
    with tempfile.TemporaryDirectory() as tmp:
        store = MessageStore(os.path.join(tmp, "messages.db"))
        now = time.time()
        for i in range(10):
            store.add_message(
                ts=now - (10 - i) * 60,
                group_id=111,
                user_id=1000 + i,
                nickname=f"成员{i}",
                content=f"第 {i} 条消息",
            )
        # 另一群一条旧消息
        store.add_message(now - 86400, 222, 9, "路人", "昨天的消息")

        msgs = store.fetch_window(111, now - 3600)
        assert len(msgs) == 10
        assert msgs[0]["content"] == "第 0 条消息"  # 按时间正序

        msgs = store.fetch_window(111, now - 3600, limit=3)
        assert len(msgs) == 3
        assert msgs[-1]["content"] == "第 9 条消息"  # 取窗口内最新的 3 条

        msgs = store.fetch_last_n(111, 5)
        assert len(msgs) == 5
        assert msgs[-1]["content"] == "第 9 条消息"

        assert store.count_since(111, now - 3600) == 10
        assert store.count_since(222, now - 3600) == 0
        assert store.groups_with_messages_since(now - 3600) == [111]

        store.set_meta("group_name:111", "测试群")
        assert store.get_meta("group_name:111") == "测试群"
        store.set_meta("group_name:111", "新名字")
        assert store.get_meta("group_name:111") == "新名字"


def test_transcript():
    # summarizer.build_transcript 不依赖网络，可直接测试
    from plugins.qq_summarizer.summarizer import build_transcript

    msgs = [
        {"ts": datetime(2026, 9, 29, 10, 0).timestamp(), "nickname": "小明", "content": "大家好"},
        {"ts": datetime(2026, 9, 29, 10, 1).timestamp(), "nickname": "小红", "content": "晚上开会" * 200},
    ]
    text = build_transcript(msgs)
    assert "小明: 大家好" in text
    assert "…(截断)" in text  # 超长消息被截断


def test_format_time_range():
    s = datetime(2026, 9, 29, 8, 0).timestamp()
    e = datetime(2026, 9, 29, 22, 0).timestamp()
    assert format_time_range(s, e) == "2026-09-29 08:00 ~ 22:00"


if __name__ == "__main__":
    test_parse_window()
    test_parse_last_n()
    test_store()
    test_transcript()
    test_format_time_range()
    print("✅ 所有测试通过")
