"""一、文件说明
    Embedding 抽象层：错误类型、Provider 接口与进程内 LRU 缓存。
    为什么把缓存放这里：重新索引时大量块文本没变，缓存命中就能少发一遍请求；缓存键区分 query/passage。

二、目录结构
    packages/harness/myagentflow/knowledge/embedding/
    ├── __init__.py
    ├── base.py  ← 本文件：接口、错误与缓存
    ├── local_provider.py  离线确定性哈希向量
    └── registry.py  选 provider、批量调用、维度校验

三、关键方法
    EmbeddingLRUCache  按 sha256(text+model+role) 缓存向量，超出容量淘汰最旧项。
    EmbeddingProvider  后端接口：embed / embed_batch。
"""

from __future__ import annotations

import hashlib
from abc import ABC, abstractmethod
from collections import OrderedDict

DEFAULT_EMBEDDING_MODEL = "hash-local-v1"
DEFAULT_EMBEDDING_DIM = 64
MAX_BATCH_SIZE = 100
_LRU_MAX_ENTRIES = 512


class EmbeddingError(RuntimeError):
    """Embedding 调用失败；网络、配置、后端缺依赖都归到这里。"""


class EmbeddingDimensionError(EmbeddingError):
    """返回向量维度与期望不一致。"""


class EmbeddingLRUCache:
    """按访问顺序淘汰的向量缓存；键里带 query/passage 角色，避免混用。"""

    def __init__(self, max_entries: int = _LRU_MAX_ENTRIES) -> None:
        self._max = max_entries
        self._store: OrderedDict[str, list[float]] = OrderedDict()

    def get(self, key: str) -> list[float] | None:
        """取缓存并移到队尾；没有返回 None。"""
        if key not in self._store:
            return None
        self._store.move_to_end(key)
        return self._store[key]

    def set(self, key: str, value: list[float]) -> None:
        """写入缓存；超出容量时淘汰队头。"""
        if key in self._store:
            self._store.move_to_end(key)
        self._store[key] = value
        while len(self._store) > self._max:
            self._store.popitem(last=False)

    def clear(self) -> None:
        """清空缓存；测试换模型时用。"""
        self._store.clear()

    def __len__(self) -> int:
        return len(self._store)


_cache = EmbeddingLRUCache()


def clear_embedding_cache() -> None:
    """清空全局缓存。"""
    _cache.clear()


def _cache_key(text: str, model: str, *, is_query: bool = False) -> str:
    """稳定缓存键：同一文本、同一模型、同一角色才复用。"""
    role = "q" if is_query else "p"
    raw = f"{text}\x00{model}\x00{role}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class EmbeddingProvider(ABC):
    """Embedding 后端接口；一个实例绑定一个模型配置。"""

    def __init__(self, model_config) -> None:
        self.model_config = model_config
        self._model_name = str(getattr(model_config, "model", "") or "").strip()

    @property
    def model_name(self) -> str:
        return self._model_name

    @abstractmethod
    async def embed(self, text: str) -> list[float]:
        """把单条文本转成稠密向量。"""

    @abstractmethod
    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """批量转换，返回顺序与输入一致。"""
