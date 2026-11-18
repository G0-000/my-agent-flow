"""消息仓储：会话正文的追加、读取、计数、清理。

为什么只追加：消息是对话的「事实记录」，改写历史会让重放、审计、分叉全部失真；
需要修正时插入一条新消息，而不是改老行。

为什么 seq 由数据库算：应用层计数器在并发下会重号；用
`MAX(seq)+1` 并在同一把锁里插入，才能保证同一会话内严格递增。
"""
from __future__ import annotations

import sqlite3
import time
from typing import Any

from myagentflow.persistence.db import db_connection_lock, get_db

CHAT_MESSAGES_SCHEMA = """
CREATE TABLE IF NOT EXISTS chat_messages (
    thread_id  TEXT NOT NULL,
    seq        INTEGER NOT NULL,
    role       TEXT NOT NULL,
    content    TEXT NOT NULL,
    created_at REAL NOT NULL,
    PRIMARY KEY (thread_id, seq)
);
CREATE INDEX IF NOT EXISTS idx_chat_messages_thread ON chat_messages(thread_id, seq);
"""


def _next_seq(db: sqlite3.Connection, thread_id: str) -> int:
    """同一会话的下一个序号；调用方必须已在锁内，否则并发插入会拿到同一个值。"""
    row = db.execute(
        "SELECT COALESCE(MAX(seq), 0) + 1 FROM chat_messages WHERE thread_id = ?",
        (thread_id,),
    ).fetchone()
    return int(row[0])


def append_message(
    thread_id: str,
    role: str,
    content: str,
    *,
    conn: sqlite3.Connection | None = None,
) -> int:
    """追加一条消息并返回它的 seq；role 只允许 user/assistant/tool（由调用方保证）。"""
    db = conn or get_db()
    with db_connection_lock():
        seq = _next_seq(db, thread_id)
        db.execute(
            "INSERT INTO chat_messages (thread_id, seq, role, content, created_at) VALUES (?, ?, ?, ?, ?)",
            (thread_id, seq, role, content, time.time()),
        )
        db.commit()
        return seq


def list_messages(
    thread_id: str,
    *,
    limit: int | None = None,
    conn: sqlite3.Connection | None = None,
) -> list[dict[str, Any]]:
    """按 seq 正序读回；limit 取「最近 N 条」而不是「最前 N 条」才有意义，故先倒序再翻转。"""
    db = conn or get_db()
    if limit is None:
        rows = db.execute(
            "SELECT seq, role, content, created_at FROM chat_messages WHERE thread_id = ? ORDER BY seq ASC",
            (thread_id,),
        ).fetchall()
    else:
        rows = db.execute(
            "SELECT seq, role, content, created_at FROM chat_messages WHERE thread_id = ? ORDER BY seq DESC LIMIT ?",
            (thread_id, limit),
        ).fetchall()[::-1]
    return [
        {"seq": r[0], "role": r[1], "content": r[2], "created_at": r[3]} for r in rows
    ]


def count_messages(thread_id: str, *, conn: sqlite3.Connection | None = None) -> int:
    db = conn or get_db()
    row = db.execute("SELECT COUNT(*) FROM chat_messages WHERE thread_id = ?", (thread_id,)).fetchone()
    return int(row[0])


def delete_messages_for_session(thread_id: str, *, conn: sqlite3.Connection | None = None) -> int:
    """整会话清空，返回删掉的行数；删会话时先调它，再删 sessions 行。"""
    db = conn or get_db()
    with db_connection_lock():
        cur = db.execute("DELETE FROM chat_messages WHERE thread_id = ?", (thread_id,))
        db.commit()
        return int(cur.rowcount or 0)
