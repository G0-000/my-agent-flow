"""一、文件说明
    向量存储：每个知识库一张普通 SQLite 表，向量用 float32 BLOB 落库，余弦在 Python 里算。
    为什么不用 sqlite-vec：本章目标是先把「写入、维度校验、按相似度召回」跑通；
    不引扩展就少一个部署依赖，规模上来后再换 vec0，接口不变。

二、目录结构
    packages/harness/myagentflow/knowledge/vector/
    ├── __init__.py
    └── sqlite_vec.py  ← 本文件：按 dataset 建表、写入、召回

三、关键方法
    VectorStore.init()       建该 dataset 的向量表，确定维度。
    VectorStore.insert_many() 批量写入；维度不一致直接报错。
    VectorStore.recall()     全表算余弦，返回 RecallHit（chunk_id/distance/score）。
"""

from __future__ import annotations

import hashlib
import math
import re
import struct
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any

from myagentflow.knowledge.owned.db import db

DEFAULT_EMBEDDING_DIM = 64
_VECTORS_TABLE_PREFIX = "evoflow_kb_vectors_"


class VectorStoreError(RuntimeError):
    """向量存储误用：维度不一致、dataset_id 为空等。"""


def _safe_table_name(dataset_id: str) -> str:
    """dataset_id 只允许字母数字下划线；其余字符折成下划线，避免 SQL 表名注入。"""
    safe = re.sub(r"[^A-Za-z0-9_]", "_", str(dataset_id or ""))
    if not safe:
        safe = hashlib.sha256(str(dataset_id).encode()).hexdigest()[:16]
    return f"{_VECTORS_TABLE_PREFIX}{safe}"


def _vectors_table_for(dataset_id: str) -> str:
    """返回该 dataset 的向量表名。"""
    return _safe_table_name(dataset_id)


@dataclass(frozen=True)
class RecallHit:
    """一条召回结果；score 是余弦相似度，distance = 1 - score。"""

    chunk_id: str
    distance: float
    score: float

    def as_dict(self) -> dict[str, Any]:
        """转成普通 dict，方便直接进入工具结果。"""
        return {
            "chunk_id": self.chunk_id,
            "distance": self.distance,
            "score": self.score,
        }


def _pack_vector(values: Sequence[float]) -> bytes:
    """打包成 little-endian float32 BLOB。"""
    return struct.pack(f"{len(values)}f", *values)


def _unpack_vector(blob: bytes, dim: int) -> list[float]:
    """按已知维度解包 float32 BLOB。"""
    return list(struct.unpack(f"{dim}f", blob))


def _cosine(a: Sequence[float], b: Sequence[float]) -> float:
    """余弦相似度；维度不等或零向量返回 0，不静默截断。"""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a <= 0 or norm_b <= 0:
        return 0.0
    return dot / (norm_a * norm_b)


class VectorStore:
    """一个 dataset 一张表的向量存储；实例绑定维度。"""

    def __init__(self, dataset_id: str, dim: int | None = None) -> None:
        if not dataset_id:
            raise VectorStoreError("dataset_id is required")
        self.dataset_id = dataset_id
        self._dim = int(dim) if dim is not None else None
        if self._dim is not None and self._dim <= 0:
            raise VectorStoreError(f"dim must be positive, got {dim}")

    @property
    def dim(self) -> int:
        """当前维度；未初始化时先按默认维度建表。"""
        if self._dim is None:
            self.init()
        return int(self._dim or DEFAULT_EMBEDDING_DIM)

    def init(self, *, name: str | None = None, embedding_model: str = "") -> int:
        """建表并返回维度；重复调用幂等。"""
        del name, embedding_model  # 本章不维护 dataset 元数据，保留签名便于后续接入
        dim = self._dim or DEFAULT_EMBEDDING_DIM
        self._dim = dim
        table = _vectors_table_for(self.dataset_id)
        with db() as conn:
            conn.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {table} (
                    chunk_id TEXT PRIMARY KEY,
                    embedding BLOB NOT NULL
                )
                """
            )
        return dim

    def insert(self, chunk_id: str, embedding: Sequence[float]) -> None:
        """写入单条向量；维度不一致直接拒绝。"""
        self.insert_many([(chunk_id, embedding)])

    def insert_many(self, items: Iterable[tuple[str, Sequence[float]]]) -> int:
        """批量写入，返回写入条数。"""
        dim = self.dim
        rows: list[tuple[str, bytes]] = []
        for chunk_id, embedding in items:
            if len(embedding) != dim:
                raise VectorStoreError(
                    f"embedding dimension mismatch for chunk {chunk_id}: expected {dim}, got {len(embedding)}"
                )
            rows.append((str(chunk_id), _pack_vector(embedding)))
        if not rows:
            return 0
        table = _vectors_table_for(self.dataset_id)
        with db() as conn:
            conn.executemany(
                f"INSERT OR REPLACE INTO {table} (chunk_id, embedding) VALUES (?, ?)",
                rows,
            )
        return len(rows)

    def delete(self, chunk_id: str) -> None:
        """删除单条向量；不存在时是 no-op。"""
        self.delete_many([chunk_id])

    def delete_many(self, chunk_ids: Iterable[str]) -> int:
        """批量删除，返回实际删除条数。"""
        ids = [str(chunk_id) for chunk_id in chunk_ids]
        if not ids:
            return 0
        table = _vectors_table_for(self.dataset_id)
        with db() as conn:
            cursor = conn.executemany(
                f"DELETE FROM {table} WHERE chunk_id = ?",
                [(chunk_id,) for chunk_id in ids],
            )
        return int(cursor.rowcount or 0)

    def delete_by_dataset(self) -> int:
        """清空该 dataset 的全部向量。"""
        table = _vectors_table_for(self.dataset_id)
        with db() as conn:
            cursor = conn.execute(f"DELETE FROM {table}")
        return int(cursor.rowcount or 0)

    def recall(
        self, query_embedding: Sequence[float], *, top_k: int = 5
    ) -> list[RecallHit]:
        """按余弦相似度召回 top_k；维度不一致直接报错。"""
        dim = self.dim
        if len(query_embedding) != dim:
            raise VectorStoreError(
                f"query embedding dimension mismatch: expected {dim}, got {len(query_embedding)}"
            )
        table = _vectors_table_for(self.dataset_id)
        with db() as conn:
            rows = conn.execute(f"SELECT chunk_id, embedding FROM {table}").fetchall()
        hits: list[RecallHit] = []
        for chunk_id, blob in rows:
            score = _cosine(query_embedding, _unpack_vector(blob, dim))
            hits.append(
                RecallHit(chunk_id=str(chunk_id), distance=1.0 - score, score=score)
            )
        hits.sort(key=lambda hit: hit.distance)
        return hits[: max(1, int(top_k))]
