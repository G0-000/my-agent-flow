"""一、文件说明
    离线 Embedding Provider：用 BLAKE2 特征哈希生成确定性向量，不下载模型、不访问网络。
    它不是语义模型：同义改写的召回弱于真实 embedding；本章用它把「缓存、维度、向量存储、
    召回」链路跑通，后续要换本地 sentence-transformers 或云 API 时只替换本文件。

二、目录结构
    packages/harness/myagentflow/knowledge/embedding/
    ├── __init__.py
    ├── base.py  接口、错误与 LRU 缓存
    ├── local_provider.py  ← 本文件：离线哈希向量
    └── registry.py  选 provider、批量调用、维度校验

三、关键方法
    LocalEmbeddingProvider.embed()       单条文本 → 64 维归一化向量。
    LocalEmbeddingProvider.embed_batch() 批量入口；逐条调用，保证顺序。
"""

from __future__ import annotations

import hashlib
import math
import re

from myagentflow.knowledge.embedding.base import (
    DEFAULT_EMBEDDING_DIM,
    EmbeddingProvider,
)

_ASCII_TOKEN = re.compile(r"[A-Za-z_][A-Za-z0-9_]{1,}")
_CJK_RUN = re.compile(r"[\u4e00-\u9fff]{2,}")
_CAMEL_BOUNDARY = re.compile(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")


class LocalEmbeddingProvider(EmbeddingProvider):
    """确定性哈希向量；同文本同模型永远得到同一向量。"""

    def __init__(self, model_config) -> None:
        super().__init__(model_config)
        raw_dim = getattr(model_config, "embedding_dim", None)
        self._dim = max(8, int(raw_dim or DEFAULT_EMBEDDING_DIM))

    async def embed(self, text: str) -> list[float]:
        """单条文本向量化；空文本返回全零向量。"""
        return self.embed_sync(text)

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """批量向量化，返回顺序与输入一致。"""
        return [self.embed_sync(text) for text in texts]

    def embed_sync(self, text: str) -> list[float]:
        """同步实现；测试与批处理都走这里，避免再包一层事件循环。"""
        vector = [0.0] * self._dim
        for token in _tokens(text):
            digest = hashlib.blake2b(token.encode("utf-8"), digest_size=16).digest()
            index = int.from_bytes(digest[:8], "big") % self._dim
            sign = 1.0 if digest[8] & 1 else -1.0
            vector[index] += sign
        norm = math.sqrt(sum(value * value for value in vector))
        if norm <= 0:
            return vector
        return [value / norm for value in vector]


def _tokens(text: str) -> list[str]:
    """抽出英文标识符、CamelCase 片段与中文二元组；只做轻量词法，不引分词库。"""
    raw = str(text or "").strip()
    if not raw:
        return []
    out: list[str] = []
    seen: set[str] = set()

    def add(token: str) -> None:
        token = token.strip()
        if len(token) < 2:
            return
        key = token.casefold()
        if key in seen:
            return
        seen.add(key)
        out.append(token)

    for match in _ASCII_TOKEN.finditer(raw):
        token = match.group(0)
        add(token)
        for piece in _CAMEL_BOUNDARY.sub(" ", token.replace("_", " ")).split():
            add(piece)
    for match in _CJK_RUN.finditer(raw):
        run = match.group(0)
        add(run)
        for index in range(len(run) - 1):
            add(run[index : index + 2])
    return out
