"""一、文件说明
    第 5 部分第 2 章：离线 Embedding、LRU 缓存、向量写入与余弦召回。

二、覆盖
    test_local_embedding_is_deterministic()     同文本同向量且已归一化。
    test_embedding_cache_skips_second_backend_call() 第二次调用只走缓存。
    test_vector_store_recall_orders_hits()       余弦召回按相似度排序。
    test_vector_store_rejects_dimension_mismatch() 写入/查询维度不一致要拒绝。

三、运行
    uv run pytest tests/chapters/test_ch05_02_vector.py -q
"""

from __future__ import annotations

import asyncio

import pytest
from myagentflow.config.paths import reset_paths_cache
from myagentflow.knowledge.embedding import registry
from myagentflow.knowledge.embedding.base import clear_embedding_cache
from myagentflow.knowledge.embedding.local_provider import LocalEmbeddingProvider
from myagentflow.knowledge.owned.db import reset_db_state_for_tests
from myagentflow.knowledge.vector.sqlite_vec import VectorStore, VectorStoreError


@pytest.fixture()
def data_dir(tmp_path, monkeypatch):
    """每个用例独立的 SQLite 数据目录。"""
    monkeypatch.setenv("MYAF_DATA_DIR", str(tmp_path))
    reset_paths_cache()
    reset_db_state_for_tests()
    clear_embedding_cache()
    yield tmp_path
    reset_db_state_for_tests()
    reset_paths_cache()


def test_local_embedding_is_deterministic():
    """同文本两次向量化结果一致，且 L2 范数为 1。"""
    provider = LocalEmbeddingProvider(registry.get_embedding_config())
    first = provider.embed_sync("FTS5 向量检索 knowledge")
    second = provider.embed_sync("FTS5 向量检索 knowledge")
    assert first == second
    assert len(first) == 64
    assert abs(sum(value * value for value in first) - 1.0) < 1e-9


def test_embedding_cache_skips_second_backend_call(monkeypatch):
    """相同文本第二次调用命中缓存，不再请求 provider。"""

    class FakeProvider:
        """记录批次数的最小替身。"""

        model_name = "fake-embedding"

        def __init__(self) -> None:
            self.calls = 0

        async def embed_batch(self, texts):
            """返回固定向量并累计调用次数。"""
            self.calls += 1
            return [[1.0, 0.0] for _ in texts]

    fake = FakeProvider()
    monkeypatch.setattr(registry, "_resolve_provider", lambda config: fake)
    config = registry.get_embedding_config()
    first = asyncio.run(registry.get_embeddings(["a", "b"], config))
    second = asyncio.run(registry.get_embeddings(["a", "b"], config))
    assert first == second
    assert fake.calls == 1


def test_vector_store_recall_orders_hits(data_dir):
    """查询向量与 c1 同向，召回第一条应是 c1，score 接近 1。"""
    store = VectorStore("vec-a", dim=3)
    store.init()
    store.insert_many([("c1", [1.0, 0.0, 0.0]), ("c2", [0.0, 1.0, 0.0])])
    hits = store.recall([1.0, 0.0, 0.0], top_k=2)
    assert [hit.chunk_id for hit in hits] == ["c1", "c2"]
    assert hits[0].score == pytest.approx(1.0)


def test_vector_store_rejects_dimension_mismatch(data_dir):
    """写入 2 维向量到 3 维表时报错，不静默补齐。"""
    store = VectorStore("vec-b", dim=3)
    store.init()
    with pytest.raises(VectorStoreError):
        store.insert("bad", [1.0, 0.0])
    with pytest.raises(VectorStoreError):
        store.recall([1.0, 0.0])
