"""沙箱策略：allow / ask / deny。

判定顺序必须是 deny → ask → allow：
先判危险命令，避免「写操作批准了，但命令其实是 rm -rf /」。
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum


class Decision(str, Enum):
    allow = "allow"
    ask = "ask"
    deny = "deny"


# 一票否决的命令特征：出现即 deny，先于「是否已批准」判断（批准也不能放行）
DANGEROUS = [
    re.compile(r"rm\s+-rf\s+/"),
    re.compile(r":\s*\(\s*\)\s*\{"),
    re.compile(r"mkfs|dd\s+if="),
    re.compile(r"curl[^|]*\|\s*(sh|bash)"),
]
# 写盘特征：命中则从 allow 降级为 ask（要人批），不直接 deny——写文件本身是正常需求
WRITE_MARKERS = [re.compile(r">\s*/"), re.compile(r"\btee\b"), re.compile(r"\bsed\s+-i\b")]


@dataclass(frozen=True)
class PolicyResult:
    decision: Decision
    reason: str


def evaluate(command: str) -> PolicyResult:
    for pat in DANGEROUS:
        if pat.search(command):
            return PolicyResult(Decision.deny, f"命中危险模式：{pat.pattern}")
    for pat in WRITE_MARKERS:
        if pat.search(command):
            return PolicyResult(Decision.ask, "疑似写文件，需要人工确认")
    return PolicyResult(Decision.allow, "未命中限制")
