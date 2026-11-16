"""会话消息表：检查点恢复用，消息存档用它。

为什么不用检查点存消息：检查点会被频繁重写、还要被剥离 transcript（见 02/01），
消息需要一个只追加、可整段回放的存储。
"""
from __future__ import annotations

import sqlite3
import time
from pathlib import Path
from typing import Any

_SCHEMA = """
CREATE TABLE IF NOT EXISTS messages (
    thread_id TEXT NOT NULL,
    seq       INTEGER NOT NULL,
    role      TEXT NOT NULL,
    content   TEXT NOT NULL,
    created_at REAL NOT NULL,
    PRIMARY KEY (thread_id, seq)
);
"""


class MessageStore:
    def __init__(self, db_path: str | Path):
        path = str(db_path)
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA busy_timeout=5000")
        self._conn.executescript(_SCHEMA)

    def append(self, thread_id: str, role: str, content: str) -> int:
        """追加一条，返回它的 seq。seq 用子查询算，避免应用层自己维护计数器。"""
        row = self._conn.execute(
            "SELECT COALESCE(MAX(seq), 0) + 1 FROM messages WHERE thread_id = ?",
            (thread_id,),
        ).fetchone()
        seq = int(row[0])
        self._conn.execute(
            "INSERT INTO messages (thread_id, seq, role, content, created_at) VALUES (?, ?, ?, ?, ?)",
            (thread_id, seq, role, content, time.time()),
        )
        self._conn.commit()
        return seq

    def history(self, thread_id: str, limit: int = 100) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT seq, role, content FROM messages WHERE thread_id = ? ORDER BY seq ASC LIMIT ?",
            (thread_id, limit),
        ).fetchall()
        return [{"seq": r[0], "role": r[1], "content": r[2]} for r in rows]
