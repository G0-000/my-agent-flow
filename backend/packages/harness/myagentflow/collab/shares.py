"""一、文件说明
    分享链接：创建、解析、撤销。
    为什么存 hash 不存 token：数据库泄露时明文 token 等于把所有人的会话送出去。

二、目录结构
    packages/harness/myagentflow/collab/
    ├── __init__.py
    ├── ledger.py  协作账本：任务认领与心跳。
    └── shares.py  ← 本文件

三、关键方法
    ShareResult  分享 token 的解析结果：状态与对应线程。
    _hash()      对分享 token 做 SHA-256；库里只存哈希，不存明文。
    ShareStore   分享记录的 SQLite 存储：创建、解析、吊销。
"""
from __future__ import annotations

import hashlib
import json
import secrets
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# 分享表只存 token 的哈希，不存明文：库泄露也拿不到可用链接（明文下发仅一次）。
_SCHEMA = """
CREATE TABLE IF NOT EXISTS shares (
    token_hash TEXT PRIMARY KEY,
    thread_id  TEXT NOT NULL,
    created_at REAL NOT NULL,
    expires_at REAL,
    revoked_at REAL,
    snapshot_json TEXT
);
"""


@dataclass(frozen=True)
class ShareResult:
    """分享 token 的解析结果：状态与对应线程。"""
    status: str          # ok | expired | revoked | missing
    thread_id: str | None = None


def _hash(token: str) -> str:
    """对分享 token 做 SHA-256；库里只存哈希，不存明文。"""
    return hashlib.sha256(token.encode()).hexdigest()


class ShareStore:
    """分享记录的 SQLite 存储：创建、解析、吊销。"""
    def __init__(self, db_path: str | Path):
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.executescript(_SCHEMA)
        # 兼容旧库：新增列不能靠 CREATE TABLE IF NOT EXISTS 补上。
        columns = {row[1] for row in self._conn.execute("PRAGMA table_info(shares)")}
        if "snapshot_json" not in columns:
            self._conn.execute("ALTER TABLE shares ADD COLUMN snapshot_json TEXT")
            self._conn.commit()

    def create(
        self,
        thread_id: str,
        ttl_seconds: int = 7 * 86400,
        *,
        snapshot: list[dict[str, Any]] | None = None,
    ) -> str:
        token = secrets.token_urlsafe(24)
        payload = json.dumps(snapshot, ensure_ascii=False) if snapshot is not None else None
        self._conn.execute(
            "INSERT INTO shares (token_hash, thread_id, created_at, expires_at, snapshot_json)"
            " VALUES (?, ?, ?, ?, ?)",
            (_hash(token), thread_id, time.time(), time.time() + ttl_seconds, payload),
        )
        self._conn.commit()
        return token          # 明文只在这里出现一次

    def snapshot(self, token: str) -> list[dict[str, Any]] | None:
        """创建分享时冻结的消息；没有快照返回 None，由调用方决定是否读实时表。"""
        row = self._conn.execute(
            "SELECT snapshot_json FROM shares WHERE token_hash = ?",
            (_hash(token),),
        ).fetchone()
        if row is None or row[0] is None:
            return None
        try:
            data = json.loads(row[0])
        except json.JSONDecodeError:
            return None
        return data if isinstance(data, list) else None

    def resolve(self, token: str, now: float | None = None) -> ShareResult:
        row = self._conn.execute(
            "SELECT thread_id, expires_at, revoked_at FROM shares WHERE token_hash = ?",
            (_hash(token),),
        ).fetchone()
        if row is None:
            return ShareResult("missing")
        thread_id, expires_at, revoked_at = row
        if revoked_at is not None:
            return ShareResult("revoked")
        if expires_at is not None and (now or time.time()) > expires_at:
            return ShareResult("expired")
        return ShareResult("ok", thread_id)

    def revoke(self, token: str) -> int:
        """吊销单个 token；返回受影响行数，0 表示 token 不存在或早已吊销。"""
        cur = self._conn.execute(
            "UPDATE shares SET revoked_at = ? WHERE token_hash = ? AND revoked_at IS NULL",
            (time.time(), _hash(token)),
        )
        self._conn.commit()
        return int(cur.rowcount or 0)

    def revoke_thread(self, thread_id: str) -> int:
        """按会话批量吊销：分享泄露时不必逐个找 token。"""
        cur = self._conn.execute(
            "UPDATE shares SET revoked_at = ? WHERE thread_id = ? AND revoked_at IS NULL",
            (time.time(), thread_id),
        )
        self._conn.commit()
        return int(cur.rowcount or 0)
