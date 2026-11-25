"""一、文件说明
    Embedding 公共入口：解析模型配置、选后端、读写 LRU 缓存、校验维度。
    调用方只认 get_embedding / get_embeddings，不直接 import 具体 provider。

二、目录结构
    packages/harness/myagentflow/knowledge/embedding/
    ├── __init__.py
    ├── base.py  接口、错误与 LRU 缓存
    ├── local_provider.py  离线确定性哈希向量
    └── registry.py  ← 本文件：选 provider、批量调用、维度校验

三、关键方法
    get_embedding()     单条入口；内部转调 get_embeddings。
    get_embeddings()    先查缓存，只把未命中的文本发给后端，再按原顺序合并。
    detect_embedding_dim() 用一条探针文本检测维度；失败退回默认值。
"""

from __future__ import annotations

from myagentflow.config.app_config import get_app_config
from myagentflow.config.model_config import ModelConfig
from myagentflow.knowledge.embedding.base import (
    DEFAULT_EMBEDDING_DIM,
    DEFAULT_EMBEDDING_MODEL,
    MAX_BATCH_SIZE,
    EmbeddingDimensionError,
    EmbeddingError,
    EmbeddingProvider,
    _cache,
    _cache_key,
)
from myagentflow.knowledge.embedding.local_provider import LocalEmbeddingProvider

DEFAULT_EMBEDDING_USE = (
    "myagentflow.knowledge.embedding.local_provider:LocalEmbeddingProvider"
)


def get_embedding_config() -> ModelConfig:
    """从应用配置挑一个 embedding 模型；没有就用离线哈希 provider 兜底。"""
    try:
        cfg = get_app_config()
        models = list(getattr(cfg, "models", None) or [])
    except Exception:
        models = []
    for model in models:
        name = str(getattr(model, "name", "") or "").lower()
        model_id = str(getattr(model, "model", "") or "").lower()
        vendor = str(getattr(model, "vendor", "") or "").lower()
        if "embedding" in name or "embedding" in model_id or vendor == "local":
            return model
    return ModelConfig(
        name="hash-local",
        vendor="local",
        use=DEFAULT_EMBEDDING_USE,
        model=DEFAULT_EMBEDDING_MODEL,
        embedding_dim=DEFAULT_EMBEDDING_DIM,
    )


def resolve_embedding_model_config(identifier: str) -> ModelConfig | None:
    """按配置名、模型 id 或显示名查模型；找不到返回 None。"""
    ident = str(identifier or "").strip()
    if not ident:
        return None
    try:
        cfg = get_app_config()
    except Exception:
        return None
    for model in getattr(cfg, "models", None) or []:
        for field in ("name", "model", "display_name"):
            if ident == str(getattr(model, field, "") or "").strip():
                return model
    return None


def _is_local_config(model_config: ModelConfig) -> bool:
    """本地 provider 的判定：vendor=local，或模型名是本章的 hash-local。"""
    vendor = str(getattr(model_config, "vendor", "") or "").strip().lower()
    model = str(getattr(model_config, "model", "") or "").strip().lower()
    return vendor == "local" or model.startswith("hash-local")


def _resolve_provider(model_config: ModelConfig) -> EmbeddingProvider:
    """按配置造 provider；本章只实现离线本地后端，云/本地模型留到后续章节。"""
    if _is_local_config(model_config):
        return LocalEmbeddingProvider(model_config)
    raise EmbeddingError(
        "本章只实现离线 hash-local embedding；请在配置里使用 vendor=local 或 hash-local 模型"
    )


async def get_embedding(
    text: str,
    model_config: ModelConfig | None = None,
    *,
    expected_dim: int | None = None,
    purpose: str | None = None,
    kb_id: str | None = None,
) -> list[float]:
    """单条文本向量化；参数语义与批量入口一致。"""
    del kb_id  # 本章没有用量计费，保留签名便于后续接入
    return (
        await get_embeddings(
            [text],
            model_config,
            expected_dim=expected_dim,
            purpose=purpose,
        )
    )[0]


async def get_embeddings(
    texts: list[str],
    model_config: ModelConfig | None = None,
    *,
    expected_dim: int | None = None,
    batch_size: int = MAX_BATCH_SIZE,
    purpose: str | None = None,
    kb_id: str | None = None,
) -> list[list[float]]:
    """批量向量化：缓存命中直接复用，未命中按 batch_size 分批请求。"""
    del kb_id  # 本章没有用量计费，保留签名便于后续接入
    if not texts:
        raise ValueError("texts must not be empty")

    config = model_config or get_embedding_config()
    provider = _resolve_provider(config)
    model_name = provider.model_name
    is_query = str(purpose or "").strip().lower() == "query"

    results: list[list[float] | None] = [None] * len(texts)
    uncached_indexes: list[int] = []
    uncached_texts: list[str] = []
    for index, text in enumerate(texts):
        key = _cache_key(text, model_name, is_query=is_query)
        hit = _cache.get(key)
        if hit is not None:
            results[index] = hit
        else:
            uncached_indexes.append(index)
            uncached_texts.append(text)

    if uncached_texts:
        size = max(1, min(int(batch_size), MAX_BATCH_SIZE))
        fetched: list[list[float]] = []
        for start in range(0, len(uncached_texts), size):
            batch = uncached_texts[start : start + size]
            vectors = await provider.embed_batch(batch)
            if len(vectors) != len(batch):
                raise EmbeddingError(
                    f"Embedding backend returned {len(vectors)} vectors for {len(batch)} inputs"
                )
            fetched.extend(vectors)

        for offset, vector in enumerate(fetched):
            if expected_dim is not None and len(vector) != expected_dim:
                raise EmbeddingDimensionError(
                    f"Embedding dimension mismatch at index {uncached_indexes[offset]}: "
                    f"expected {expected_dim}, got {len(vector)}"
                )
            index = uncached_indexes[offset]
            results[index] = vector
            _cache.set(
                _cache_key(uncached_texts[offset], model_name, is_query=is_query),
                vector,
            )

    out: list[list[float]] = []
    for vector in results:
        if vector is None:  # pragma: no cover - 防御式兜底
            raise EmbeddingError("Internal error: unfilled embedding slot")
        out.append(vector)
    return out


async def detect_embedding_dim(
    model_config: ModelConfig | None = None,
    *,
    fallback: int = DEFAULT_EMBEDDING_DIM,
) -> int:
    """用一条探针文本测维度；失败返回 fallback，不阻断建库。"""
    config = model_config or get_embedding_config()
    try:
        vector = await get_embedding("dimension probe", config, purpose="probe")
        return len(vector) if vector else fallback
    except Exception:
        return fallback
