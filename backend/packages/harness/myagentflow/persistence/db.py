"""应用 SQLite 的连接与事务：整个进程共用一条连接。

为什么共用一条：应用库是单文件，多个写连接会互相抢锁；一条连接 + 一把进程内锁，
把并发问题收在一个地方，SQLite 的 WAL 再兜住跨进程读写。

模块位置（调用方向自上而下）:

    app/gateway/routers/chat.py
        └─ persistence/session_repositories.py      会话标题与时间戳
        └─ persistence/chat_message_repositories.py 消息追加与读回
              └─ persistence/db.py  ← 本文件          get_db / db_connection_lock
                    └─ config/app_config.py            storage.sqlite_path
"""
from __future__ import annotations

import os
import sqlite3
import threading
from pathlib import Path

_lock = threading.RLock()
_conn: sqlite3.Connection | None = None

# 测试用：指向临时库文件；不设就走 AppConfig.storage.sqlite_path
DB_PATH_ENV = "MYAF_DB_PATH"


def _resolve_db_path() -> Path:
    env_path = os.getenv(DB_PATH_ENV, "").strip()
    if env_path:
        return Path(env_path).expanduser()
    from myagentflow.config.app_config import get_app_config

    return Path(get_app_config().storage.sqlite_path).expanduser()


def db_connection_lock() -> threading.RLock:
    """写操作的进程内互斥锁；多线程同时 append 时靠它保证 seq 不撞。"""
    return _lock


def _ensure_schema(conn: sqlite3.Connection) -> None:
    """建各仓储的表；延迟 import 避免 `db ← repositories → db` 的循环。"""
    from myagentflow.persistence.chat_message_repositories import CHAT_MESSAGES_SCHEMA
    from myagentflow.persistence.session_repositories import SESSIONS_SCHEMA

    conn.executescript(SESSIONS_SCHEMA + CHAT_MESSAGES_SCHEMA)


def get_db() -> sqlite3.Connection:
    """取共享连接；第一次调用时建目录、开 WAL、建表。"""
    global _conn
    with _lock:
        if _conn is None:
            path = _resolve_db_path()
            path.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(str(path), check_same_thread=False)
            conn.execute("PRAGMA journal_mode=WAL")      # 读写不互相阻塞
            conn.execute("PRAGMA busy_timeout=5000")     # 跨进程抢锁最多等 5s
            _ensure_schema(conn)
            _conn = conn
        return _conn


def reset_db() -> None: 
    """关掉并丢弃共享连接（测试换库文件、或进程收尾时用）。"""
    global _conn
    with _lock:
        if _conn is not None:
            _conn.close()
            _conn = None
