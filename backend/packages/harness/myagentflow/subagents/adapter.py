"""一、文件说明
    外部 Agent 适配：把 A2A 响应变成内部子代理结果。
    为什么单独一层：外部协议随时会变，变化只该影响这个文件，
    不该渗透到计划执行、记忆写入这些内部模块。

二、目录结构
    packages/harness/myagentflow/subagents/
    ├── __init__.py
    ├── adapter.py  ← 本文件
    ├── registry.py  子代理注册表：谁能干什么，谁来干。
    └── summarize.py  子代理结果汇总：只回填「结论 + 证据 + 失败原因」。

三、关键方法
    ExternalAgent  外部子代理的连接信息：名字、地址、超时。
    to_request()   把任务与上下文包成外部代理的请求体。
    to_summary()   把外部代理的原始响应收敛成统一摘要。
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from myagentflow.subagents.summarize import summarize


@dataclass(frozen=True)
class ExternalAgent:
    """外部子代理的连接信息：名字、地址、超时。"""
    name: str
    endpoint: str
    timeout: float = 30.0


def to_request(task: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
    """把任务与上下文包成外部代理的请求体。"""
    return {"task": task, "context": context or {}}


def to_summary(agent: ExternalAgent, raw: dict[str, Any]) -> str:
    """把外部代理的原始响应收敛成统一摘要。"""
    if "error" in raw:
        return summarize(agent.name, str(raw["error"]), ok=False)
    text = raw.get("result") or raw.get("content") or json.dumps(raw, ensure_ascii=False)
    return summarize(agent.name, str(text), ok=True)
