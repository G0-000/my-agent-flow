"""子代理结果汇总：只回填「结论 + 证据 + 失败原因」。

为什么不回填全文：子代理动辄跑几十步，全文回填会直接把主上下文顶到压缩阈值。
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
