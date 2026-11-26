"""一、文件说明
    记忆抽取与写回：把一段对话压成几条 atom，再交给 facade 落库。
    为什么不让模型直接写 SQLite：模型只产出 JSON，字段校验和写库在代码里做，
    低置信度噪声、超长内容、非法 layer 都不能进库。

二、目录结构
    packages/harness/myagentflow/memory/
    ├── queue.py    ← 防抖队列
    └── updater.py  ← 本文件：抽取 prompt + JSON 校验 + 写回

三、关键方法
    extract_atoms()  调模型抽 atom；容忍 ```json 围栏，解析失败返回空列表
    apply_atoms()    逐条校验后写库，低置信度由 facade 自行丢弃
    flush_queue()    取到期项 → 抽取 → 写回 → ack；失败退避
"""
from __future__ import annotations

import json
import re
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from myagentflow.memory import facade
from myagentflow.memory.queue import MemoryUpdateQueue

_EXTRACT_PROMPT = (
    "你是记忆抽取器。从对话里抽“以后还用得上”的稳定事实，不要抽寒暄和临时状态。\n"
    "只输出 JSON 数组，每项字段：content（一句话事实）、layer（semantic/episodic）、"
    "kind（fact/preference/decision）、importance（0~1）、confidence（0~1）、"
    "subject_key（可选，同一主题的稳定键）。\n"
    "没有可记内容就输出 []。不要解释，不要 Markdown 以外的东西。"
)

_VALID_LAYERS = {"semantic", "episodic", "procedural"}
_VALID_KINDS = {"fact", "preference", "decision", "event", "task"}
_MAX_CONTENT = 600
_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


def _parse_json_array(text: str) -> list[dict[str, Any]]:
    """先按围栏取，再退化到首个 [ ... ]；解析失败返回空列表。"""
    raw = str(text or "").strip()
    candidates = [m.strip() for m in _FENCE.findall(raw)]
    if not candidates and raw:
        start, end = raw.find("["), raw.rfind("]")
        if start != -1 and end > start:
            candidates.append(raw[start : end + 1])
    for cand in candidates:
        try:
            data = json.loads(cand)
        except json.JSONDecodeError:
            continue
        if isinstance(data, list):
            return [d for d in data if isinstance(d, dict)]
    return []


def _clamp01(value: Any, default: float) -> float:
    try:
        f = float(value)
    except (TypeError, ValueError):
        return default
    return min(1.0, max(0.0, f))


def validate_atom(raw: dict[str, Any]) -> dict[str, Any] | None:
    """字段校验：缺 content 或 layer/kind 非法就丢弃，不做“猜一个”。"""
    content = str(raw.get("content") or "").strip()
    if not content:
        return None
    if len(content) > _MAX_CONTENT:
        content = content[:_MAX_CONTENT]
    layer = str(raw.get("layer") or "semantic").lower()
    kind = str(raw.get("kind") or "fact").lower()
    if layer not in _VALID_LAYERS:
        layer = "semantic"
    if kind not in _VALID_KINDS:
        kind = "fact"
    return {
        "content": content,
        "layer": layer,
        "kind": kind,
        "importance": _clamp01(raw.get("importance"), 0.5),
        "confidence": _clamp01(raw.get("confidence"), 0.7),
        "subject_key": str(raw.get("subject_key") or "").strip()[:120],
    }


def extract_atoms(model: Any, text: str) -> list[dict[str, Any]]:
    """调模型抽 atom；模型抛错由调用方处理，这里只做协议容错。"""
    body = str(text or "").strip()
    if not body:
        return []
    reply = model.invoke([
        SystemMessage(content=_EXTRACT_PROMPT),
        HumanMessage(content=f"对话记录：\n{body}"),
    ])
    content = getattr(reply, "content", reply)
    if isinstance(content, list):
        content = "".join(str(p) for p in content)
    atoms = [a for a in (validate_atom(r) for r in _parse_json_array(str(content))) if a]
    return atoms


def apply_atoms(namespace: str, atoms: list[dict[str, Any]], *, source: str = "extract") -> list[str]:
    """写回 atom；返回真实落库的 id 列表，被 facade 判噪声的不会出现。"""
    written: list[str] = []
    for a in atoms:
        atom_id = facade.remember(
            namespace,
            a["content"],
            layer=a["layer"],
            kind=a["kind"],
            importance=a["importance"],
            confidence=a["confidence"],
            subject_key=a["subject_key"],
            source=source,
        )
        if atom_id:
            written.append(atom_id)
    return written


def flush_queue(
    queue: MemoryUpdateQueue,
    model: Any,
    *,
    now: float | None = None,
    retry_delay: float = 5.0,
) -> dict[str, Any]:
    """跑一批到期项；一条失败不影响同批其它项。"""
    batch = queue.due(now)
    stats = {"processed": 0, "written": 0, "failed": 0, "skipped": 0}
    for item in batch:
        stats["processed"] += 1
        try:
            atoms = extract_atoms(model, item.text)
        except Exception:
            queue.fail(item)
            queue.retry_later(item, delay=retry_delay, now=now)
            stats["failed"] += 1
            continue
        if not atoms:
            stats["skipped"] += 1
            queue.ack(item)
            continue
        stats["written"] += len(apply_atoms(item.namespace, atoms))
        queue.ack(item)
    return stats
