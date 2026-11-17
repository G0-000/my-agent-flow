"""检查点提供者：单例 + 一次性上下文（memory / sqlite / postgres）。

为什么要多这一层：
1) checkpointer 是带连接的活对象，随手 new 会到处漏连接；
2) 配置会变（切后端、换库文件），必须能不重启进程就重建。
"""
from __future__ import annotations

import contextlib
import logging
import os
import sqlite3
import threading
from collections.abc import Iterator

from langgraph.types import Checkpointer

logger = logging.getLogger(__name__)

# 错误文案写成常量：报错时直接把「装什么」告诉人
SQLITE_INSTALL = "需要 langgraph-checkpoint-sqlite。安装：uv add langgraph-checkpoint-sqlite"
# 每条报错都写清「装什么」，而不是只抛一句 NotImplementedError
POSTGRES_INSTALL = (
    "需要 langgraph-checkpoint-postgres。"
    "安装：uv add langgraph-checkpoint-postgres psycopg[binary] psycopg-pool"
)
# postgres 没有连接串就无法连库，这条错误必须点名环境变量
POSTGRES_CONN_REQUIRED = "postgres 后端必须提供连接串（MYAF_CHECKPOINT_PG_DSN）"


def _checkpointer_config():
    """配置来源对齐 EvoFlow：读 AppConfig.checkpointer（type / connection_string）。

    环境变量只在测试里当覆盖用（`MYAF_CHECKPOINTER` / `MYAF_CHECKPOINT_SQLITE_PATH`），
    生产路径一律走 config.yaml。
    """
    from myagentflow.config.app_config import get_app_config
    from myagentflow.config.checkpointer_config import CheckpointerConfig

    cfg = get_app_config().checkpointer
    backend = (os.getenv("MYAF_CHECKPOINTER") or "").strip().lower()
    if backend:
        return CheckpointerConfig(
            type=backend,
            connection_string=os.getenv("MYAF_CHECKPOINT_SQLITE_PATH") or cfg.connection_string,
        )
    return cfg


def _backend() -> str:
    """读后端类型；默认 memory —— 保证「什么配置都没有」也能跑起来。"""
    return _checkpointer_config().type


def _sqlite_path() -> str:
    """检查点库文件路径。放 .myaf/ 下，跟仓库源码分开。"""
    return _checkpointer_config().connection_string or ".myaf/checkpoints.sqlite"


def _pg_dsn() -> str:
    return os.getenv("MYAF_CHECKPOINT_PG_DSN", "").strip()


def _build(backend: str) -> Checkpointer:
    """按 backend 造一个全新的 saver（不缓存）。"""
    if backend == "memory":
        from langgraph.checkpoint.memory import InMemorySaver

        return InMemorySaver()

    if backend == "sqlite":
        try:
            from langgraph.checkpoint.sqlite import SqliteSaver
        except ImportError as exc:  # 缺包给「怎么装」
            raise RuntimeError(SQLITE_INSTALL) from exc

        path = _sqlite_path()
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)

        # 长连接而非每次 new：SqliteSaver 持有 connection，
        # 频繁开关会导致 setup 反复执行，并发时还会互相锁表。
        conn = sqlite3.connect(path, check_same_thread=False)
        # WAL：读不阻塞写、写不阻塞读。检查点是「短写 + 高频读」，收益最大。
        conn.execute("PRAGMA journal_mode=WAL")
        # busy_timeout：并发写最多等 5s 再报 locked，不设就直接抛 database is locked。
        conn.execute("PRAGMA busy_timeout=5000")

        saver = SqliteSaver(conn)
        saver.setup()  # 建表：v3.x 实测为 checkpoints + writes（版本不同表名会变，以实际为准）
        return saver

    if backend == "postgres":
        dsn = _pg_dsn()
        if not dsn:
            raise RuntimeError(POSTGRES_CONN_REQUIRED)
        try:
            from langgraph.checkpoint.postgres import PostgresSaver
        except ImportError as exc:
            raise RuntimeError(POSTGRES_INSTALL) from exc

        saver = PostgresSaver.from_conn_string(dsn)
        saver.setup()
        return saver

    raise RuntimeError(f"未知的 checkpointer 后端：{backend}")


_lock = threading.RLock()
_singleton: Checkpointer | None = None
_singleton_key: tuple[str, str] | None = None


def _close(saver: Checkpointer) -> None:
    """关掉 saver 底下的真实连接。不是所有后端都暴露 .conn，所以探测着来。"""
    conn = getattr(saver, "conn", None)
    if conn is not None:
        with contextlib.suppress(Exception):
            conn.close()


def get_checkpointer() -> Checkpointer:
    """取全局 saver：同一份配置返回同一对象，配置变了自动重建。"""
    global _singleton, _singleton_key
    backend = _backend()
    key = (backend, _pg_dsn() or _sqlite_path())

    with _lock:  # 两个线程同时首次调用时，只允许一个真的去 build
        if _singleton is not None and _singleton_key == key:
            return _singleton
        if _singleton is not None:  # 旧配置：先关连接
            _close(_singleton)
        _singleton = _build(backend)
        _singleton_key = key
        logger.info("checkpointer 初始化完成 backend=%s", backend)
        return _singleton


def reset_checkpointer() -> None:
    """测试与「运行中改配置」用：关连接 + 清空单例。"""
    global _singleton, _singleton_key
    with _lock:
        if _singleton is not None:
            _close(_singleton)
        _singleton = None
        _singleton_key = None


@contextlib.contextmanager
def checkpointer_context() -> Iterator[Checkpointer]:
    """一次性 saver：进入时新建，退出时必定关闭。

    适用：CLI 跑一次图就退出、测试要隔离连接。
    不适用：常驻 Gateway —— 反复建连接会让 WAL 文件持续增长。
    """
    saver = _build(_backend())
    try:
        yield saver
    finally:
        _close(saver)
