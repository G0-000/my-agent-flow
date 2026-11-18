"""一、文件说明
    资产与反思：一张表管三类东西。
    为什么不拆三张表：它们都要「按 thread 查、按时间排」，
    拆开以后每次跨类检索都要 UNION。

二、目录结构
    packages/harness/myagentflow/memory/
    ├── __init__.py
    ├── agent_memory.py  两层记忆：agent 级跨任务，thread 级随线程删。
    └── assets.py  ← 本文件

三、关键方法
    Asset       一条资产：产物/待办/反思，带引用。
    AssetStore  资产表的 SQLite 读写。
"""
from __future__ import annotations

import sqlite3
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

# 线程产物表：记录这条线程生成过哪些文件/图片，ref 指向实际存储位置。
# 组合索引 (thread_id, kind, created_at) 对「按线程列最近的产物」最省。
_SCHEMA = """
CREATE TABLE IF NOT EXISTS assets (
    id         TEXT PRIMARY KEY,
    thread_id  TEXT NOT NULL,
    kind       TEXT NOT NULL,
    title      TEXT NOT NULL,
    ref        TEXT,
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_assets_thread ON assets(thread_id, kind, created_at);
"""


@dataclass(frozen=True)
class Asset:
    """一条资产：产物/待办/反思，带引用。"""
    thread_id: str
    kind: str        # artifact | todo | reflection
    title: str
    ref: str | None = None


class AssetStore:
    """资产表的 SQLite 读写。"""
    def __init__(self, db_path: str | Path):
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.executescript(_SCHEMA)

    def add(self, asset: Asset) -> str:
        if asset.kind not in {"artifact", "todo", "reflection"}:
            raise ValueError(f"未知资产类型：{asset.kind}")
        ident = uuid.uuid4().hex
        self._conn.execute(
            "INSERT INTO assets (id, thread_id, kind, title, ref, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (ident, asset.thread_id, asset.kind, asset.title, asset.ref, time.time()),
        )
        self._conn.commit()
        return ident

    def list(self, thread_id: str, kind: str | None = None) -> list[dict]:
        if kind:
            rows = self._conn.execute(
                "SELECT id, kind, title, ref FROM assets WHERE thread_id=? AND kind=? ORDER BY created_at DESC",
                (thread_id, kind),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT id, kind, title, ref FROM assets WHERE thread_id=? ORDER BY created_at DESC",
                (thread_id,),
            ).fetchall()
        return [{"id": r[0], "kind": r[1], "title": r[2], "ref": r[3]} for r in rows]
