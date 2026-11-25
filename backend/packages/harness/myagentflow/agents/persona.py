"""一、文件说明
    人格：可组合片段 + 预算内保序拼装。
    为什么分片段：人格要能按场景覆盖（比如客服场景换语气），
    一整段提示词没法局部替换。

二、目录结构
    packages/harness/myagentflow/agents/
    ├── lead_agent/  单节点 Agent 图
    ├── memory/      agent / task 两层记忆
    ├── middlewares/ 中间件链与审计
    └── persona.py  ← 本文件

三、关键方法
    Fragment   提示词片段：文本加优先级，用来拼 system prompt。
    compose()  按优先级从高到低拼片段；超预算整段丢弃，不截半句。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Fragment:
    """提示词片段：文本加优先级，用来拼 system prompt。"""

    name: str
    text: str
    priority: int = 10  # 数字越大越先保留


def compose(fragments: list[Fragment], max_chars: int = 2000) -> str:
    """按优先级从高到低拼片段；超预算整段丢弃，不截半句。"""
    ordered = sorted(fragments, key=lambda f: -f.priority)
    kept, used = [], 0
    for f in ordered:
        if used + len(f.text) > max_chars:
            continue  # 低优先级的直接丢，不做半句截断
        kept.append(f.text)
        used += len(f.text)
    return "\n\n".join(kept)
