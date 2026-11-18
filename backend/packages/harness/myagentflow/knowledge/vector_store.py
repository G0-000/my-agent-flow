"""一、文件说明
    向量存储：SQLite + Python 余弦。
    为什么先不上向量库：几千块规模下，一次全表扫描 <10ms，
    引入 FAISS 只会让部署多一个依赖。

二、目录结构
    packages/harness/myagentflow/knowledge/
    ├── __init__.py
    ├── chunker.py  切块：先按标题分段，再按窗口滑。
    ├── map.py  知识地图：文档 → 标题 → 块 id。
    └── vector_store.py  ← 本文件

三、关键方法
    _cos()
    VectorStore
"""
from __future__ import annotations

import json
import math
import sqlite3
from pathlib import Path

# 知识库分块表：vector 以 JSON 文本落库（SQLite 没有向量类型），相似度在 Python 里算。
_SCHEMA = """
CREATE TABLE IF NOT EXISTS chunks (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    doc_id    TEXT NOT NULL,
    heading   TEXT NOT NULL,
    text      TEXT NOT NULL,
    vector    TEXT NOT NULL
);
"""


def _cos(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(y * y for y in b)) or 1.0
    return dot / (na * nb)


class VectorStore:
    def __init__(self, db_path: str | Path):
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.executescript(_SCHEMA)

    def add(self, doc_id: str, heading: str, text: str, vector: list[float]) -> None:
        self._conn.execute(
            "INSERT INTO chunks (doc_id, heading, text, vector) VALUES (?, ?, ?, ?)",
            (doc_id, heading, text, json.dumps(vector)),
        )
        self._conn.commit()

    def search(self, query_vec: list[float], top_k: int = 3) -> list[dict]:
        rows = self._conn.execute("SELECT doc_id, heading, text, vector FROM chunks").fetchall()
        scored = [
            {"doc_id": r[0], "heading": r[1], "text": r[2], "score": _cos(query_vec, json.loads(r[3]))}
            for r in rows
        ]
        return sorted(scored, key=lambda x: x["score"], reverse=True)[:top_k]
