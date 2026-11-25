"""一、文件说明
    Owned Knowledge 的 SQLite 连接：一个进程一条连接，schema 只初始化一次。
    为什么单独一个库：知识库索引与聊天消息的生命周期不同，放在 owned.sqlite 里，
    重建/删除知识库不会碰到会话数据。

二、目录结构
    packages/harness/myagentflow/knowledge/owned/
    ├── __init__.py
    ├── db.py  ← 本文件：连接、锁、初始化
    ├── ids.py  id 与时间
    ├── schema.py  kb_* / kg_* 表结构
    ├── service.py  知识库、文档、目录与块
    └── kg.py  实体图节点与边

三、关键方法
    owned_db_path()          默认 $MYAF_DATA_DIR/knowledge/owned.sqlite。
    db()                     共享连接的上下文管理器；退出时提交，异常回滚。
    reset_db_state_for_tests() 关连接并清缓存，测试换数据目录用。
"""

from __future__ import annotations

import sqlite3
import threading
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from pathlib import Path

from myagentflow.config.paths import get_paths
from myagentflow.knowledge.owned.schema import ensure_schema

_lock = threading.RLock()
_conn: sqlite3.Connection | None = None
_schema_ready = False


def owned_db_path() -> Path:
    """知识库库文件：{base_dir}/knowledge/owned.sqlite。"""
    return get_paths().base_dir / "knowledge" / "owned.sqlite"


def _connect() -> sqlite3.Connection:
    """打开连接：WAL + busy_timeout + Row 工厂。"""
    path = owned_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), check_same_thread=False, timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


def _ensure_conn() -> sqlite3.Connection:
    """取连接；首次或 schema 版本变化时初始化表。"""
    global _conn, _schema_ready
    if _conn is None:
        _conn = _connect()
    if not _schema_ready:
        ensure_schema(_conn)
        _schema_ready = True
    return _conn


@contextmanager
def db() -> Iterator[sqlite3.Connection]:
    """共享连接上下文；整个代码块串行执行，避免同库多写互相抢锁。"""
    with _lock:
        conn = _ensure_conn()
        try:
            yield conn
            if conn.in_transaction:
                conn.commit()
        except Exception:
            if conn.in_transaction:
                conn.rollback()
            raise


def reset_db_state_for_tests() -> None:
    """测试辅助：关闭共享连接，下次调用重新打开并建表。"""
    global _conn, _schema_ready
    with _lock:
        if _conn is not None:
            with suppress(Exception):  # 关连接失败不应影响测试清理
                _conn.close()
            _conn = None
        _schema_ready = False
