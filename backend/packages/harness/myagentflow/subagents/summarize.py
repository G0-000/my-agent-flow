"""一、文件说明
    子代理结果汇总：只回填「结论 + 证据 + 失败原因」。
    为什么不回填全文：子代理动辄跑几十步，全文回填会直接把主上下文顶到压缩阈值。

二、目录结构
    packages/harness/myagentflow/subagents/
    ├── __init__.py
    ├── adapter.py  外部 Agent 适配：把 A2A 响应变成内部子代理结果。
    ├── registry.py  子代理注册表：谁能干什么，谁来干。
    └── summarize.py  ← 本文件

三、关键方法
    summarize()
"""
from __future__ import annotations

LIMIT = 600


def summarize(name: str, result: str, ok: bool = True, evidence: list[str] | None = None) -> str:
    head = f"[子代理 {name}] {'完成' if ok else '失败'}"
    body = result.strip()
    if len(body) > LIMIT:
        body = body[:LIMIT] + "…（已截断）"
    lines = [head, body]
    if evidence:
        lines.append("证据：" + "；".join(evidence[:5]))
    return "\n".join(lines)
