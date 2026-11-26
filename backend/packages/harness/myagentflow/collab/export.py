"""一、文件说明
    分享视图的导出与脱敏：分享是给外部看的，不能把密钥和本机路径带出去。
    为什么脱敏放在导出层而不是消息表：消息表是内部事实，改写会破坏审计；
    只在「离开系统」的边界上打码。

二、目录结构
    packages/harness/myagentflow/collab/
    ├── shares.py  分享 token 存储
    └── export.py  ← 本文件：脱敏 + Markdown/JSON 渲染
"""
from __future__ import annotations

import json
import re
from typing import Any

# 只处理高置信度模式：宁可漏掉一个奇怪格式，也不要把正常正文改成乱码。
_SECRET_PATTERNS = (
    (re.compile(r"sk-[A-Za-z0-9_\-]{8,}"), "sk-***"),
    (
        re.compile(r"(?i)\b(api[_-]?key|access[_-]?token|token|password|secret|authorization)\b(\s*[=:]\s*)\S+"),
        r"\1\2***",
    ),
)
_HOME_PATTERNS = (
    re.compile(r"/Users/[^/\s\"']+"),
    re.compile(r"/home/[^/\s\"']+"),
)


def redact_text(text: str) -> str:
    """密钥与本机用户目录打码；返回新字符串，不修改入参。"""
    out = str(text or "")
    for pattern, replacement in _SECRET_PATTERNS:
        out = pattern.sub(replacement, out)
    for pattern in _HOME_PATTERNS:
        out = pattern.sub("~", out)
    return out


def redact_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """逐条脱敏，保留 seq/role 等结构字段。"""
    cleaned: list[dict[str, Any]] = []
    for row in messages:
        item = dict(row)
        item["content"] = redact_text(str(item.get("content") or ""))
        cleaned.append(item)
    return cleaned


def render_markdown(thread_id: str, messages: list[dict[str, Any]]) -> str:
    """Markdown 导出：角色加粗，正文逐段；适合直接发给别人看。"""
    lines = [f"# 会话 {thread_id}", ""]
    for row in redact_messages(messages):
        role = str(row.get("role") or "unknown")
        lines.append(f"**{role}**")
        lines.append("")
        lines.append(str(row.get("content") or ""))
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def render_json(thread_id: str, messages: list[dict[str, Any]]) -> str:
    """JSON 导出：保留 seq，便于程序再处理。"""
    payload = {"thread_id": thread_id, "messages": redact_messages(messages)}
    return json.dumps(payload, ensure_ascii=False, indent=2)
