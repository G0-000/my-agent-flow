"""外部 Agent 适配：把 A2A 响应变成内部子代理结果。

为什么单独一层：外部协议随时会变，变化只该影响这个文件，
不该渗透到计划执行、记忆写入这些内部模块。
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from myagentflow.subagents.summarize import summarize


@dataclass(frozen=True)
class ExternalAgent:
    name: str
    endpoint: str
    timeout: float = 30.0


def to_request(task: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"task": task, "context": context or {}}


def to_summary(agent: ExternalAgent, raw: dict[str, Any]) -> str:
    if "error" in raw:
        return summarize(agent.name, str(raw["error"]), ok=False)
    text = raw.get("result") or raw.get("content") or json.dumps(raw, ensure_ascii=False)
    return summarize(agent.name, str(text), ok=True)
