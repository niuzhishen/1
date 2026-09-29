"""时间窗口解析：把「2小时 / 30分钟 / 今天 / 昨天 / 120」这类表述转成时间戳区间。"""

from __future__ import annotations

import re
import time
from datetime import datetime, timedelta
from typing import Optional, Tuple

_UNIT_SECONDS = {
    "秒": 1,
    "s": 1,
    "分": 60,
    "分钟": 60,
    "m": 60,
    "min": 60,
    "时": 3600,
    "小时": 3600,
    "h": 3600,
    "hour": 3600,
    "hours": 3600,
    "天": 86400,
    "日": 86400,
    "d": 86400,
    "day": 86400,
    "days": 86400,
    "周": 604800,
    "星期": 604800,
    "w": 604800,
}

_NUM_UNIT_RE = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*([a-zA-Z\u4e00-\u9fff]*)\s*$")


def parse_window(
    text: str, now: Optional[datetime] = None
) -> Optional[Tuple[float, float]]:
    """解析时间窗口描述，返回 (start_ts, end_ts)；无法解析返回 None。

    支持：
      - 「今天」「昨天」
      - 「2小时」「30分钟」「半天」「1天」「2h」「3d」
      - 纯数字 → 按分钟算，如「120」= 最近 120 分钟
    """
    now = now or datetime.now()
    now_ts = now.timestamp()
    text = (text or "").strip()
    if not text:
        return None

    if text in ("今天", "今日"):
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        return start.timestamp(), now_ts

    if text in ("昨天", "昨日"):
        today0 = now.replace(hour=0, minute=0, second=0, microsecond=0)
        return (today0 - timedelta(days=1)).timestamp(), today0.timestamp()

    if text == "半天":
        return now_ts - 12 * 3600, now_ts

    m = _NUM_UNIT_RE.match(text)
    if m:
        num = float(m.group(1))
        unit = (m.group(2) or "分钟").strip().lower()
        seconds = _UNIT_SECONDS.get(unit)
        if seconds is None:
            return None
        return now_ts - num * seconds, now_ts

    return None


def parse_last_n(text: str) -> Optional[int]:
    """解析「最近 200 条 / 200条消息」这类条数描述。"""
    m = re.search(r"(\d+)\s*条", text or "")
    if m:
        n = int(m.group(1))
        return max(1, min(n, 5000))
    return None


def format_time_range(start_ts: float, end_ts: float) -> str:
    fmt = "%m-%d %H:%M"
    start = datetime.fromtimestamp(start_ts)
    end = datetime.fromtimestamp(end_ts)
    if start.date() == end.date():
        return f"{start.strftime('%Y-%m-%d')} {start.strftime('%H:%M')} ~ {end.strftime('%H:%M')}"
    return f"{start.strftime(fmt)} ~ {end.strftime(fmt)}"
