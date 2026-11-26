"""一、文件说明
    记忆注入：把 standing 记忆和按 query 召回的 atom 拼成一个可放进 prompt 的数据块。
    为什么放在 memory 层：召回、预算、快照是同一件事；调用方只该拿到「一段文本」。

二、目录结构
    packages/harness/myagentflow/memory/
    ├── injection.py  ← 本文件
    ├── facade.py
    └── recall_snapshot.py

三、关键方法
    build_memory_context()  召回 + 常驻记忆 + 快照，返回拼好的文本。
"""
from __future__ import annotations

from myagentflow.memory import facade, recall_snapshot


def build_memory_context(
    namespaces: list[str],
    query: str,
    *,
    thread_id: str = "",
    top_k: int = 6,
    max_chars: int = 1000,
    standing_max_chars: int = 1200,
) -> str:
    """返回可直接放进 system prompt 的记忆块；空召回返回空串。"""
    ns = [n for n in namespaces if n]
    if not ns:
        return ""
    standing_atoms = facade.get_core(ns, max_chars=standing_max_chars)
    hits = facade.recall(ns, query, top_k=top_k, max_chars=max_chars)
    standing = facade.format_atoms_block(standing_atoms, title="memory")
    archival = facade.format_atoms_block(hits, title="memory_archival")
    recall_snapshot.record_thread_recall(
        thread_id,
        query=query,
        standing_preview=standing[:400],
        hits=hits,
        source="turn",
    )
    return "\n\n".join(part for part in (standing, archival) if part)
