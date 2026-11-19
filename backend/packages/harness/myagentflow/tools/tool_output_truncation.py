"""一、文件说明
    工具输出截断：超预算时保留头 + 尾，中间用 marker 标掉多少 token。
    为什么保留头尾：头通常是命令/文件开头与错误摘要，尾是最新输出；
    只留头会丢掉「刚发生了什么」，只留尾会丢掉上下文。

二、目录结构
    packages/harness/myagentflow/tools/
    ├── builtins/
    ├── host_direct/
    ├── large_result_store.py   超大结果落盘
    ├── registry.py
    └── tool_output_truncation.py  ← 本文件：内联截断

三、关键方法
    truncate_text_to_token_budget()       中间截断到 max_tokens。
    formatted_truncate_tool_output()      截断并加「原始 token/行数」头。
"""
from __future__ import annotations

from myagentflow.context.tool_tokens import _CHARS_PER_TOKEN, count_tool_tokens

_OMITTED_MARKER_TEMPLATE = "... {omitted} tokens truncated ..."


def truncate_text_to_token_budget(text: str, max_tokens: int) -> str:
    """中间截断到 max_tokens：保留头尾，中间放省略标记。"""
    raw = str(text or "")
    if not raw or max_tokens <= 0:
        return ""
    if count_tool_tokens(raw) <= max_tokens:
        return raw

    # 预算小到连头尾都放不下：退化成「取头部固定字符 + 提示」，别返回空串
    if len(raw) <= _CHARS_PER_TOKEN * max_tokens // 2:
        half = max(128, len(raw) // 2)
        return raw[:half] + "\n\n[Truncated for tool output budget.]"

    omitted = max(0, count_tool_tokens(raw) - max_tokens)
    marker = _OMITTED_MARKER_TEMPLATE.format(omitted=omitted)

    # 二分「头尾各留多少字符」：token 估算随字符单调增，适合二分
    lo, hi = 0, len(raw)
    head_len = 0
    while lo <= hi:
        mid = (lo + hi) // 2
        head = raw[:mid]
        tail = raw[len(raw) - mid :] if mid < len(raw) else ""
        candidate = f"{head}\n\n{marker}\n\n{tail}" if tail else f"{head}\n\n{marker}"
        if count_tool_tokens(candidate) <= max_tokens:
            head_len = mid
            lo = mid + 1
        else:
            hi = mid - 1

    if head_len <= 0:
        return raw[: max(128, _CHARS_PER_TOKEN * max_tokens // 4)] + "\n\n[Truncated for tool output budget.]"

    head = raw[:head_len]
    tail = raw[-head_len:] if head_len < len(raw) else ""
    if tail and tail != head:
        return f"{head}\n\n{marker}\n\n{tail}"
    return f"{head}\n\n{marker}"


def formatted_truncate_tool_output(text: str, max_tokens: int) -> str:
    """截断并加「原始 token/行数」头，让模型知道内容不完整。"""
    raw = str(text or "")
    if not raw:
        return raw
    original_token_count = count_tool_tokens(raw)
    if original_token_count <= max_tokens:
        return raw
    total_lines = len(raw.splitlines()) or 1
    body = truncate_text_to_token_budget(raw, max_tokens)
    return (
        f"Warning: truncated output (original token count: {original_token_count})\n"
        f"Total output lines: {total_lines}\n\n{body}"
    )
