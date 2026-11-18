"""一、文件说明
    会话仓储：一条会话一行，负责标题与时间戳。
    为什么会话和消息分两张表：会话是「目录」，消息是「正文」；
    删会话要能留下审计（先删消息、再删行），两者的生命周期不绑在一起。

二、目录结构
    packages/harness/myagentflow/persistence/
    ├── __init__.py
    ├── chat_message_repositories.py  消息仓储：会话正文的追加、读取、计数、清理。
    ├── db.py  应用 SQLite 的连接与事务：整个进程共用一条连接。
    └── session_repositories.py  ← 本文件

三、关键方法
    upsert_session_row()            建或更新会话：已存在就刷新 updated_at，标题只在传入非空时改。
    get_session_row_for_ui()        按 session_key 取一行；不存在返回 None（不抛异常，调用方据此决定建不建）。
    list_sessions_for_ui()          最近有更新的会话，按 updated_at 倒序；limit 限制条数，防止首页一次拉全库。
    delete_sessions_by_thread_id()  删一条会话，返回删掉的行数（0 表示本来就不存在）。
"""
from __future__ import annotations

import sqlite3
import time
from typing import Any

from myagentflow.persistence.db import db_connection_lock, get_db

SESSIONS_SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    session_key TEXT PRIMARY KEY,
    title       TEXT NOT NULL DEFAULT '',
    created_at  REAL NOT NULL,
    updated_at  REAL NOT NULL
);
"""


def upsert_session_row(
    session_key: str,
    *,
    title: str | None = None,
    conn: sqlite3.Connection | None = None,
) -> None:
    """建或更新会话：已存在就刷新 updated_at，标题只在传入非空时改。"""
    db = conn or get_db()
    now = time.time()
    with db_connection_lock():
        row = db.execute("SELECT title, created_at FROM sessions WHERE session_key = ?", (session_key,)).fetchone()
        if row is None:
            db.execute(
                "INSERT INTO sessions (session_key, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
                (session_key, title or "", now, now),
            )
        else:
            new_title = title if title else row[0]
            db.execute(
                "UPDATE sessions SET title = ?, updated_at = ? WHERE session_key = ?",
                (new_title, now, session_key),
            )
        db.commit()


def get_session_row_for_ui(session_key: str, *, conn: sqlite3.Connection | None = None) -> dict[str, Any] | None:
    """按 session_key 取一行；不存在返回 None（不抛异常，调用方据此决定建不建）。"""
    db = conn or get_db()
    row = db.execute(
        "SELECT session_key, title, created_at, updated_at FROM sessions WHERE session_key = ?",
        (session_key,),
    ).fetchone()
    if row is None:
        return None
    return {"session_key": row[0], "title": row[1], "created_at": row[2], "updated_at": row[3]}


def list_sessions_for_ui(limit: int = 50, *, conn: sqlite3.Connection | None = None) -> list[dict[str, Any]]:
    """最近有更新的会话，按 updated_at 倒序；limit 限制条数，防止首页一次拉全库。"""
    db = conn or get_db()
    rows = db.execute(
        "SELECT session_key, title, created_at, updated_at FROM sessions ORDER BY updated_at DESC LIMIT ?",
        (limit,),
    ).fetchall()
    return [
        {"session_key": r[0], "title": r[1], "created_at": r[2], "updated_at": r[3]} for r in rows
    ]


def delete_sessions_by_thread_id(thread_id: str, *, conn: sqlite3.Connection | None = None) -> int:
    """删一条会话，返回删掉的行数（0 表示本来就不存在）。"""
    db = conn or get_db()
    with db_connection_lock():
        cur = db.execute("DELETE FROM sessions WHERE session_key = ?", (thread_id,))
        db.commit()
        return int(cur.rowcount or 0)
