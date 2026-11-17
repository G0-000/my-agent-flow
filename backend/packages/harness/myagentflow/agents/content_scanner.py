"""内容扫描：命中即阻断，返回降级文本。

为什么返回字符串而不是抛异常：
外部内容（网页、文件、记忆）随时可能是恶意的，抛异常会让「一次注入」等于一次拒绝服务；
返回 BLOCKED 文本，模型能看见「这段被拦了」，流程还能继续。
"""
from __future__ import annotations

import re

# 注入特征表：第一列是威胁名（写进 BLOCKED 文案，便于排查），第二列是正则。
PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("prompt_injection", re.compile(r"ignore\s+(all\s+)?(previous|above|prior)\s+instructions", re.IGNORECASE)),
    ("role_hijack", re.compile(r"you\s+are\s+now\s+", re.IGNORECASE)),
    ("deception_hide", re.compile(r"do\s+not\s+tell\s+the\s+user", re.IGNORECASE)),
    ("sys_prompt_override", re.compile(r"system\s+prompt\s+override", re.IGNORECASE)),
    ("disregard_rules", re.compile(r"disregard\s+(your|all|any)\s+instructions", re.IGNORECASE)),
    ("bypass_restrictions", re.compile(r"act\s+as\s+if\s+you\s+have\s+no\s+restrictions", re.IGNORECASE)),
    ("html_comment_injection", re.compile(r"<!--[^>]*(ignore|override|system|secret)[^>]*-->", re.IGNORECASE)),
    ("hidden_div", re.compile(r"display\s*:\s*none", re.IGNORECASE)),
    ("translate_execute", re.compile(r"translate\s+.*\s+(then|and)\s+(execute|run)", re.IGNORECASE)),
    ("exfil_curl", re.compile(r"curl\s+.*\$\s*(\w*)(KEY|TOKEN|SECRET)", re.IGNORECASE)),
    ("read_secrets", re.compile(r"(cat|open|read)\s+.*(\.env|id_rsa|\.pgpass|credentials)", re.IGNORECASE)),
    ("case_bypass", re.compile(r"o\s*v\s*e\s*r\s*r\s*i\s*d\s*e", re.IGNORECASE)),
]

# 零宽 / 双向控制字符：肉眼看不见，却能让「删掉前半句」这类指令藏在正常文本里
INVISIBLE = ["\u200b", "\u200c", "\u200d", "\u2060", "\ufeff",
             "\u202a", "\u202b", "\u202c", "\u202d", "\u202e"]

# 命中后返回的降级文本：带威胁名、说明「未加载」，让模型知道这段被拦过
BLOCKED = "[BLOCKED: source contained potential prompt injection ({threat}). Content was not loaded.]"


def scan(text: str, source: str = "content") -> tuple[bool, str]:
    """返回 (是否命中, 处理后的文本)。命中时文本被整体替换。"""
    if not text:
        return False, text
    if any(ch in text for ch in INVISIBLE):
        return True, BLOCKED.format(threat="invisible_unicode")

    for threat, pattern in PATTERNS:
        if pattern.search(text):
            return True, BLOCKED.format(threat=threat)

    return False, text


def scan_memory_entries(entries: list[str]) -> list[str]:
    """逐条扫描记忆：命中只废掉这一条，不废整份记忆。"""
    out = []
    for entry in entries:
        hit, _ = scan(entry)
        out.append("[BLOCKED MEMORY ENTRY — contains prompt injection patterns]" if hit else entry)
    return out
