"""一、文件说明
    记忆门面：remember / recall / get_core / forget / consolidate。
    为什么不让调用方直接碰 store：门面负责置信度过滤、预算裁剪、归档过滤，
    这些规则一旦散到调用点就会各写一套。

二、目录结构
    packages/harness/myagentflow/memory/
    ├── __init__.py
    ├── namespaces.py
    ├── store.py       原子表
    ├── facade.py      ← 本文件
    ├── consolidate.py 巩固
    └── recall_snapshot.py

三、关键方法
    remember()          写一条记忆；低置信度且无来源的噪声直接丢。
    recall()            关键词召回 + 归档过滤 + 字符预算。
    get_core()          pin / 偏好 / 短背景，供 standing 注入。
    forget()            软删一条。
    consolidate()       显式巩固命名空间；本章不派发异步任务。
    format_atoms_block() 把 atom 列表格式化成可注入文本。
"""

from __future__ import annotations

import logging
from typing import Any

from myagentflow.memory import store as mem_store

logger = logging.getLogger(__name__)


def _get_archive_floor() -> float:
    """归档下限：低于它的非 pin 记忆默认不召回。"""
    return 0.15


def remember(
    namespace: str,
    content: str,
    *,
    layer: str = "semantic",
    kind: str = "fact",
    summary: str = "",
    importance: float | None = None,
    confidence: float | None = None,
    vitality: float = 1.0,
    subject_key: str = "",
    evidence: dict[str, Any] | None = None,
    tags: list[Any] | None = None,
    source: str = "",
    pin: bool = False,
    atom_id: str | None = None,
    embedding: list[float] | None = None,
) -> str | None:
    """写一条记忆；返回 atom id，低置信度噪声返回 None。"""
    conf = mem_store.clamp01(confidence if confidence is not None else 0.7, 0.7)
    # 低置信度、非 pin、无 subject、非用户/手工来源 → 视为噪声
    if (
        conf < 0.55
        and not pin
        and not subject_key
        and source not in {"user", "manual", "migrate"}
    ):
        return None
    imp = mem_store.clamp01(importance if importance is not None else conf, 0.5)
    return mem_store.upsert_atom(
        namespace_id=namespace,
        content=content,
        layer=layer,
        kind=kind,
        summary=summary,
        importance=imp,
        confidence=conf,
        vitality=vitality,
        subject_key=subject_key,
        evidence=evidence,
        tags=tags,
        source=source,
        pin=pin,
        atom_id=atom_id,
        embedding=embedding,
    )


def forget(atom_id: str, *, mode: str = "soft") -> bool:
    """删一条；当前只有 soft，mode 参数为签名兼容。"""
    del mode
    return mem_store.soft_delete_atom(atom_id)


def consolidate(
    namespace: str,
    *,
    trigger: str = "manual",
    async_job: bool = False,
) -> dict[str, Any]:
    """巩固一个命名空间；async_job 需要任务队列，本章未实现。"""
    ns = (namespace or "").strip()
    if not ns:
        return {"ok": False, "error": "namespace required"}
    if async_job:
        return {"ok": False, "error": "async_job not implemented"}
    from myagentflow.memory.consolidate import consolidate_namespace

    return consolidate_namespace(ns, trigger=trigger)


def recall(
    namespaces: list[str],
    query: str,
    *,
    layers: list[str] | None = None,
    top_k: int = 8,
    max_chars: int = 1000,
    query_embedding: list[float] | None = None,
) -> list[dict[str, Any]]:
    """关键词召回；向量参数保留但当前不参与。"""
    del query_embedding
    ns = [n for n in namespaces if n]
    q = (query or "").strip()
    if not ns:
        return []
    if not q:
        hits: list[dict[str, Any]] = []
        for n in ns:
            hits.extend(mem_store.list_namespace_atoms(n, layers=layers, limit=top_k))
        hits.sort(
            key=lambda a: (float(a.get("importance") or 0), a.get("updated_at") or ""),
            reverse=True,
        )
        return _budget(hits[:top_k], max_chars)

    kw = mem_store.search_keyword_ns(ns, q, top_k=max(top_k * 3, 12), layers=layers)
    mem_store.touch_accessed([a["id"] for a in kw if a.get("id")])
    return _budget(_filter_archived(kw, q)[:top_k], max_chars)


def get_core(
    namespaces: list[str],
    *,
    max_chars: int = 1200,
    min_confidence: float = 0.0,
) -> list[dict[str, Any]]:
    """pin + 偏好/行为 + 短背景，供 standing 注入。"""
    prefer_kinds = {"preference", "behavior"}
    context_kinds = {"context"}
    picked: list[dict[str, Any]] = []
    seen: set[str] = set()
    for ns in namespaces:
        if not ns:
            continue
        for atom in mem_store.list_namespace_atoms(ns, pinned_only=True, limit=40):
            if atom["id"] in seen:
                continue
            if float(atom.get("confidence") or 0) < min_confidence:
                continue
            kind = str(atom.get("kind") or "")
            if kind.startswith("section:") or kind == "knowledge":
                continue
            seen.add(atom["id"])
            picked.append(atom)
        for atom in mem_store.list_namespace_atoms(
            ns, layers=["semantic", "procedural"], limit=60
        ):
            if atom["id"] in seen:
                continue
            if float(atom.get("confidence") or 0) < max(min_confidence, 0.7):
                continue
            kind = str(atom.get("kind") or "").strip().lower()
            if kind in prefer_kinds:
                pass
            elif kind in context_kinds:
                text = str(atom.get("content") or "")
                if len(text) > 180 or float(atom.get("importance") or 0) < 0.75:
                    continue
            else:
                continue
            if float(atom.get("importance") or 0) < 0.65 and not atom.get("pin"):
                continue
            seen.add(atom["id"])
            picked.append(atom)
    out: list[dict[str, Any]] = []
    used = 0
    for atom in picked:
        text = (atom.get("summary") or atom.get("content") or "").strip()
        if not text:
            continue
        if used + len(text) > max_chars and out:
            break
        out.append(atom)
        used += len(text) + 1
    return out


def _filter_archived(atoms: list[dict[str, Any]], query: str) -> list[dict[str, Any]]:
    """丢掉低活力 atom，除非 pin 或查询词强命中。"""
    floor = _get_archive_floor()
    q = (query or "").strip().lower()
    out: list[dict[str, Any]] = []
    for atom in atoms:
        if atom.get("pin"):
            out.append(atom)
            continue
        vit = float(atom.get("vitality") or 1.0)
        if vit >= floor:
            out.append(atom)
            continue
        if not q:
            continue
        text = f"{atom.get('summary') or ''} {atom.get('content') or ''}".lower()
        tokens = [t for t in q.split() if len(t) > 1]
        if tokens and all(t in text for t in tokens):
            out.append(atom)
    return out


def format_atoms_block(
    atoms: list[dict[str, Any]],
    *,
    title: str = "Memory",
) -> str:
    """格式化成 <memory> 块；空列表返回空串。"""
    if not atoms:
        return ""
    lines: list[str] = []
    for atom in atoms:
        text = (atom.get("summary") or atom.get("content") or "").strip()
        if not text:
            continue
        layer = atom.get("layer") or ""
        kind = atom.get("kind") or ""
        prefix = ""
        if layer or kind:
            prefix = f"[{layer}:{kind}] " if kind else f"[{layer}] "
        pin = "★ " if atom.get("pin") else ""
        lines.append(f"- {pin}{prefix}{text}")
    if not lines:
        return ""
    body = "\n".join(lines)
    tag = title.lower().replace(" ", "_")
    return f"<{tag}>\n{body}\n</{tag}>"


def _budget(atoms: list[dict[str, Any]], max_chars: int) -> list[dict[str, Any]]:
    """按字符预算裁剪；至少保留第一条。"""
    out: list[dict[str, Any]] = []
    used = 0
    for atom in atoms:
        text = (atom.get("summary") or atom.get("content") or "").strip()
        if not text:
            continue
        if used + len(text) > max_chars and out:
            break
        out.append(atom)
        used += len(text) + 1
    return out
