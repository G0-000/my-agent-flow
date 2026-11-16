"""人格：可组合片段 + 预算内保序拼装。

为什么分片段：人格要能按场景覆盖（比如客服场景换语气），
一整段提示词没法局部替换。
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Fragment:
    name: str
    text: str
    priority: int = 10        # 数字越大越先保留


def compose(fragments: list[Fragment], max_chars: int = 2000) -> str:
    ordered = sorted(fragments, key=lambda f: -f.priority)
    kept, used = [], 0
    for f in ordered:
        if used + len(f.text) > max_chars:
            continue           # 低优先级的直接丢，不做半句截断
        kept.append(f.text)
        used += len(f.text)
    return "\n\n".join(kept)
