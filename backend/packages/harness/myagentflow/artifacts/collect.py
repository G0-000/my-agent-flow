"""从工具调用中收集产物：只认显式契约，不猜正文里的路径。

为什么保守：工具输出是模型可读的文本，里面出现 `/tmp/a` 不代表它是本轮产物；
把每个路径都登记成产物，会让前端出现一堆无关文件。只接受三种来源：
1. 工具返回结构化 ``{"artifacts": [...]}``；
2. 已知写文件工具的入参 path；
3. 输出里的 http(s) 链接。
"""
from __future__ import annotations

import json
import re
from typing import Any

from myagentflow.artifacts.chat_artifact import (
    artifact_state_key,
    normalize_chat_artifacts,
)

_URL = re.compile(r"https?://[^\s)\]\"'<>]+", re.IGNORECASE)
_WRITE_TOOLS = frozenset({"write_file"})


def _structured(output: Any) -> list[Any]:
    """只接受带 artifacts 键的 dict，或「像产物」的 dict 列表。"""
    if isinstance(output, dict):
        arts = output.get("artifacts")
        return arts if isinstance(arts, list) else []
    if isinstance(output, list):
        return [x for x in output if isinstance(x, dict) and any(k in x for k in ("path", "url"))]
    text = str(output or "").strip()
    if not text.startswith(("{", "[")):
        return []
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return []
    return _structured(data)


def collect_artifacts(tool_name: str, args: dict[str, Any], output: Any) -> list[dict[str, Any]]:
    """返回归一化后的产物列表；没有就返回空列表。"""
    raw: list[Any] = list(_structured(output))
    if tool_name in _WRITE_TOOLS:
        path = str((args or {}).get("path") or "").strip()
        if path:
            raw.append({"type": "file", "path": path})
    if isinstance(output, str):
        raw.extend({"type": "url", "url": u} for u in _URL.findall(output))
    return normalize_chat_artifacts(raw)


def merge_into(state: dict[str, dict[str, Any]], items: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """按稳定键写进状态；返回新 dict，方便节点作为增量返回。"""
    out = dict(state or {})
    for item in items:
        key = artifact_state_key(item)
        if key:
            out[key] = item
    return out
