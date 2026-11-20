"""一、文件说明
    命名空间记忆巩固：合并重复 / 同 subject 的 atom（确定性，不调 LLM）。
    为什么不用 LLM：巩固是每轮都可能跑的后台动作，模型调用会带来成本与抖动；
    先用文本重叠做确定性合并，语义级合并留给后续阶段。

二、目录结构
    packages/harness/myagentflow/memory/
    ├── __init__.py
    ├── store.py       原子表
    ├── facade.py      门面
    ├── consolidate.py ← 本文件
    └── recall_snapshot.py

三、关键方法
    text_overlap()            token + 中文二元组的 Jaccard，取较大值。
    consolidate_namespace()   合并同 subject / 高相似 atom，返回统计。
    should_enqueue_threshold() 条数达到阈值才建议入队。
"""

from __future__ import annotations

import re
from typing import Any

from myagentflow.memory import store as mem_store
from myagentflow.timeutil import utc_now_iso_z

_TOKEN_RE = re.compile(r"[\w\u4e00-\u9fff]+", re.UNICODE)
# 只对语义/流程层做模糊合并；episodic 是事件流水，合并会丢时间线
_MERGE_LAYERS = frozenset({"semantic", "procedural"})
_DEFAULT_SIMILARITY = 0.72
_THRESHOLD_ATOMS = 10


def _tokens(text: str) -> set[str]:
    return {t.lower() for t in _TOKEN_RE.findall(text or "") if len(t) > 1}


def _char_bigrams(text: str) -> set[str]:
    s = re.sub(r"\s+", "", (text or "").lower())
    if len(s) < 2:
        return {s} if s else set()
    return {s[i : i + 2] for i in range(len(s) - 1)}


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else 0.0


def text_overlap(a: str, b: str) -> float:
    """token Jaccard 与中文二元组 Jaccard 取较大值。"""
    return max(
        _jaccard(_tokens(a), _tokens(b)), _jaccard(_char_bigrams(a), _char_bigrams(b))
    )


def _similarity(a: dict[str, Any], b: dict[str, Any]) -> float:
    return text_overlap(str(a.get("content") or ""), str(b.get("content") or ""))


def _keep_prefer(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    """保留优先级：pin > importance > confidence > 更新时间。"""
    if bool(a.get("pin")) != bool(b.get("pin")):
        return a if a.get("pin") else b
    ka = (
        float(a.get("importance") or 0),
        float(a.get("confidence") or 0),
        str(a.get("updated_at") or ""),
    )
    kb = (
        float(b.get("importance") or 0),
        float(b.get("confidence") or 0),
        str(b.get("updated_at") or ""),
    )
    return a if ka >= kb else b


def _merge_content(keep: dict[str, Any], drop: dict[str, Any]) -> str:
    """合并正文：短文本已包含在长文本里就不重复拼。"""
    k = str(keep.get("content") or "").strip()
    d = str(drop.get("content") or "").strip()
    if not d:
        return k
    if d in k:
        return k
    if k in d:
        return d
    return f"{k}\n{d}" if k else d


def consolidate_namespace(
    namespace_id: str,
    *,
    trigger: str = "manual",
    similarity_merge: float | None = None,
    decay_factor: float | None = None,
    archive_vitality: float | None = None,
    gc_min_confidence: float | None = None,
    gc_idle_days: int | None = None,
) -> dict[str, Any]:
    """合并一个命名空间；后四个参数保留签名，衰减/GC 本章未实现。"""
    del decay_factor, archive_vitality, gc_min_confidence, gc_idle_days
    sim_th = (
        float(similarity_merge) if similarity_merge is not None else _DEFAULT_SIMILARITY
    )
    ns = mem_store.ensure_namespace(namespace_id)
    atoms = mem_store.list_namespace_atoms(ns, limit=2000)
    stats: dict[str, Any] = {
        "namespace": ns,
        "trigger": trigger,
        "scanned": len(atoms),
        "subject_merged": 0,
        "similarity_merged": 0,
        "decayed": 0,
        "gc_deleted": 0,
        "skipped_pin": 0,
        "updated_at": utc_now_iso_z(),
    }

    # A1. 同 subject_key：保留最优，其余软删
    by_subject: dict[str, list[dict[str, Any]]] = {}
    for atom in atoms:
        sk = str(atom.get("subject_key") or "").strip()
        if sk:
            by_subject.setdefault(sk, []).append(atom)
    active_ids = {a["id"] for a in atoms}
    for group in by_subject.values():
        live = [a for a in group if a["id"] in active_ids]
        if len(live) < 2:
            continue
        keep = live[0]
        for cand in live[1:]:
            keep = _keep_prefer(keep, cand)
        for cand in live:
            if cand["id"] == keep["id"]:
                continue
            if cand.get("pin") and not keep.get("pin"):
                stats["skipped_pin"] += 1
                continue
            merged = _merge_content(keep, cand)
            if merged != str(keep.get("content") or ""):
                mem_store.update_atom_fields(
                    keep["id"],
                    content=merged,
                    importance=max(
                        float(keep.get("importance") or 0),
                        float(cand.get("importance") or 0),
                    ),
                    confidence=max(
                        float(keep.get("confidence") or 0),
                        float(cand.get("confidence") or 0),
                    ),
                )
                keep["content"] = merged
            mem_store.supersede_atom(
                cand["id"], keep["id"], source="consolidate_subject"
            )
            active_ids.discard(cand["id"])
            stats["subject_merged"] += 1

    # A2. 相似合并：只在 semantic/procedural，且没有 subject_key 的条目
    atoms = mem_store.list_namespace_atoms(ns, limit=2000)
    active_ids = {a["id"] for a in atoms}
    merge_pool = [
        a
        for a in atoms
        if a["id"] in active_ids
        and str(a.get("layer") or "") in _MERGE_LAYERS
        and not str(a.get("subject_key") or "").strip()
    ]
    merge_pool.sort(
        key=lambda a: (float(a.get("importance") or 0), str(a.get("updated_at") or "")),
        reverse=True,
    )
    consumed: set[str] = set()
    for i, a in enumerate(merge_pool):
        if a["id"] in consumed or a["id"] not in active_ids:
            continue
        for b in merge_pool[i + 1 :]:
            if b["id"] in consumed or b["id"] not in active_ids:
                continue
            if str(a.get("layer")) != str(b.get("layer")):
                continue
            if _similarity(a, b) < sim_th:
                continue
            keep, drop = (a, b) if _keep_prefer(a, b) is a else (b, a)
            if drop.get("pin") and not keep.get("pin"):
                stats["skipped_pin"] += 1
                continue
            merged = _merge_content(keep, drop)
            mem_store.update_atom_fields(
                keep["id"],
                content=merged,
                importance=max(
                    float(keep.get("importance") or 0),
                    float(drop.get("importance") or 0),
                ),
                confidence=max(
                    float(keep.get("confidence") or 0),
                    float(drop.get("confidence") or 0),
                ),
            )
            keep["content"] = merged
            mem_store.supersede_atom(drop["id"], keep["id"], source="consolidate_sim")
            consumed.add(drop["id"])
            active_ids.discard(drop["id"])
            stats["similarity_merged"] += 1

    return {"ok": True, **stats}


def should_enqueue_threshold(namespace_id: str) -> bool:
    """条数达到阈值才建议入队巩固，避免每条新记忆都跑一遍。"""
    return mem_store.count_active_atoms(namespace_id) >= _THRESHOLD_ATOMS
