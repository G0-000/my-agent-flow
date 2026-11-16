"""分享链接：创建、解析、撤销。

为什么存 hash 不存 token：数据库泄露时明文 token 等于把所有人的会话送出去。
"""
from __future__ import annotations

import hashlib
import secrets
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS shares (
    token_hash TEXT PRIMARY KEY,
    thread_id  TEXT NOT NULL,
    created_at REAL NOT NULL,
    expires_at REAL,
    revoked_at REAL
);
"""


@dataclass(frozen=True)
class ShareResult:
    status: str          # ok | expired | revoked | missing
    thread_id: str | None = None


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class ShareStore:
    def __init__(self, db_path: str | Path):
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.executescript(_SCHEMA)

    def create(self, thread_id: str, ttl_seconds: int = 7 * 86400) -> str:
        token = secrets.token_urlsafe(24)
        self._conn.execute(
            "INSERT INTO shares (token_hash, thread_id, created_at, expires_at) VALUES (?, ?, ?, ?)",
            (_hash(token), thread_id, time.time(), time.time() + ttl_seconds),
        )
        self._conn.commit()
        return token          # 明文只在这里出现一次

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

    def revoke(self, token: str) -> None:
        self._conn.execute(
            "UPDATE shares SET revoked_at = ? WHERE token_hash = ?",
            (time.time(), _hash(token)),
        )
        self._conn.commit()
