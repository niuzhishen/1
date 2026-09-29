"""SQLite 消息存储。"""

from __future__ import annotations

import os
import sqlite3
import threading
import time
from typing import Optional


class MessageStore:
    def __init__(self, path: str):
        parent = os.path.dirname(path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        self._lock = threading.Lock()
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        with self._lock:
            self.conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS messages (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts          REAL    NOT NULL,
                    group_id    INTEGER NOT NULL,
                    user_id     INTEGER NOT NULL,
                    nickname    TEXT    NOT NULL DEFAULT '',
                    content     TEXT    NOT NULL DEFAULT '',
                    raw_type    TEXT    NOT NULL DEFAULT 'message'
                );
                CREATE INDEX IF NOT EXISTS idx_messages_group_time
                    ON messages(group_id, ts);
                CREATE TABLE IF NOT EXISTS meta (
                    key   TEXT PRIMARY KEY,
                    value TEXT
                );
                """
            )
            self.conn.commit()

    # ---- 写入 ----
    def add_message(
        self,
        ts: float,
        group_id: int,
        user_id: int,
        nickname: str,
        content: str,
        raw_type: str = "message",
    ) -> None:
        with self._lock:
            self.conn.execute(
                "INSERT INTO messages (ts, group_id, user_id, nickname, content, raw_type)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (ts, group_id, user_id, nickname, content, raw_type),
            )
            self.conn.commit()

    # ---- 查询 ----
    def fetch_window(
        self,
        group_id: int,
        start_ts: float,
        end_ts: Optional[float] = None,
        limit: Optional[int] = None,
    ) -> list[dict]:
        """取 [start, end] 内的消息；带 limit 时取窗口内最新的 limit 条（按时间正序返回）。"""
        end_ts = end_ts if end_ts is not None else time.time()
        with self._lock:
            if limit is not None:
                rows = self.conn.execute(
                    "SELECT * FROM ("
                    " SELECT * FROM messages"
                    " WHERE group_id = ? AND ts >= ? AND ts <= ?"
                    " ORDER BY ts DESC LIMIT ?"
                    ") t ORDER BY ts ASC",
                    (group_id, start_ts, end_ts, limit),
                ).fetchall()
            else:
                rows = self.conn.execute(
                    "SELECT * FROM messages"
                    " WHERE group_id = ? AND ts >= ? AND ts <= ?"
                    " ORDER BY ts ASC",
                    (group_id, start_ts, end_ts),
                ).fetchall()
        return [dict(r) for r in rows]

    def fetch_last_n(
        self, group_id: int, n: int, before_ts: Optional[float] = None
    ) -> list[dict]:
        before_ts = before_ts if before_ts is not None else time.time()
        with self._lock:
            rows = self.conn.execute(
                "SELECT * FROM ("
                " SELECT * FROM messages"
                " WHERE group_id = ? AND ts <= ?"
                " ORDER BY ts DESC LIMIT ?"
                ") t ORDER BY ts ASC",
                (group_id, before_ts, n),
            ).fetchall()
        return [dict(r) for r in rows]

    def count_since(self, group_id: int, start_ts: float) -> int:
        with self._lock:
            row = self.conn.execute(
                "SELECT COUNT(*) AS c FROM messages WHERE group_id = ? AND ts >= ?",
                (group_id, start_ts),
            ).fetchone()
        return int(row["c"])

    def groups_with_messages_since(self, start_ts: float) -> list[int]:
        with self._lock:
            rows = self.conn.execute(
                "SELECT DISTINCT group_id FROM messages WHERE ts >= ? ORDER BY group_id",
                (start_ts,),
            ).fetchall()
        return [int(r["group_id"]) for r in rows]

    # ---- meta（群名缓存等）----
    def get_meta(self, key: str) -> Optional[str]:
        with self._lock:
            row = self.conn.execute(
                "SELECT value FROM meta WHERE key = ?", (key,)
            ).fetchone()
        return row["value"] if row else None

    def set_meta(self, key: str, value: str) -> None:
        with self._lock:
            self.conn.execute(
                "INSERT INTO meta (key, value) VALUES (?, ?)"
                " ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, value),
            )
            self.conn.commit()
