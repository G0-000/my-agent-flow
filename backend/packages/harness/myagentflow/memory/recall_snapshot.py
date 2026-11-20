"""一、文件说明
    每线程召回快照：记录「这一轮到底召回了哪些记忆」。
    为什么要有：注入透明与排错；同一轮内 prompt 要稳定，不能边生成边改召回。

二、目录结构
    packages/harness/myagentflow/memory/
    ├── __init__.py
    ├── store.py       原子表
    ├── facade.py      门面
    ├── recall_snapshot.py  ← 本文件
    └── consolidate.py

三、关键方法
    record_thread_recall()  写一份快照，最多 24 条命中。
    get_thread_recall()     取快照（副本，防外部改内部）。
    clear_thread_recall()   删某线程快照。
"""

from __future__ import annotations

import threading
from typing import Any

from myagentflow.timeutil import utc_now_iso_z

_lock = threading.Lock()
_by_thread: dict[str, dict[str, Any]] = {}
_MAX_THREADS = 500


def _trim() -> None:
    """超过 500 个线程时按 updated_at 丢最旧的。"""
    if len(_by_thread) <= _MAX_THREADS:
        return
    ordered = sorted(
        _by_thread.items(),
        key=lambda kv: str(kv[1].get("updated_at") or ""),
    )
    for key, _ in ordered[: max(1, len(ordered) - _MAX_THREADS)]:
        _by_thread.pop(key, None)


def record_thread_recall(
    thread_id: str,
    *,
    query: str = "",
    standing_preview: str = "",
    hits: list[dict[str, Any]] | None = None,
    source: str = "turn",
) -> None:
    """写快照；空 thread_id 直接忽略。"""
    tid = (thread_id or "").strip()
    if not tid:
        return
    compact: list[dict[str, Any]] = []
    for h in hits or []:
        if not isinstance(h, dict):
            continue
        text = str(h.get("summary") or h.get("content") or "").strip()
        if not text:
            continue
        compact.append(
            {
                "id": str(h.get("id") or ""),
                "namespace_id": str(h.get("namespace_id") or ""),
                "layer": str(h.get("layer") or ""),
                "kind": str(h.get("kind") or ""),
                "content": text[:240],
                "pin": bool(h.get("pin")),
                "source_channel": str(h.get("source_channel") or ""),
            }
        )
        if len(compact) >= 24:
            break
    with _lock:
        _by_thread[tid] = {
            "thread_id": tid,
            "query": (query or "")[:500],
            "standing_preview": (standing_preview or "").strip()[:800],
            "hits": compact,
            "hit_count": len(compact),
            "source": source,
            "updated_at": utc_now_iso_z(),
        }
        _trim()


def get_thread_recall(thread_id: str) -> dict[str, Any] | None:
    """取快照副本；没有返回 None。"""
    tid = (thread_id or "").strip()
    if not tid:
        return None
    with _lock:
        snap = _by_thread.get(tid)
        return dict(snap) if snap else None


def clear_thread_recall(thread_id: str) -> None:
    """删某线程快照。"""
    tid = (thread_id or "").strip()
    if not tid:
        return
    with _lock:
        _by_thread.pop(tid, None)


def reset_for_tests() -> None:
    """测试清空全局快照。"""
    with _lock:
        _by_thread.clear()
