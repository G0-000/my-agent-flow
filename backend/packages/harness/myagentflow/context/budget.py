"""一、文件说明
    上下文预算：估算、阈值、封顶。
    为什么要有绝对上限：
    模型窗口写着 256K，但实测 334K ctx 时 TTFT 会飙到 10.9s，
    所以「比例阈值」必须再被一个绝对值压住。

二、目录结构
    packages/harness/myagentflow/context/
    ├── __init__.py
    └── budget.py  ← 本文件

三、关键方法
    estimate_tokens()    粗估：中文约 1 字 1 token，英文约 4 字符 1 token。宁可高估。
    compact_threshold()  压缩触发阈值：上下文比例与绝对上限取较小值。
    should_compact()     当前 token 数是否达到压缩阈值。
    refill_target()      压缩后的回填目标：按同轮/跨轮比例把阈值换算成可用预算。
"""
from __future__ import annotations

# 模型没写 context_length 时按 256K 估：宁可高估窗口，也不要低估后把请求截断
DEFAULT_CONTEXT = 256_000
# 用到窗口 90% 就触发压缩：留 10% 给「压缩本身也要占上下文」
AUTO_COMPACT_RATIO = 0.9
# 绝对上限 150K：实测超过这个量 TTFT 会从 2s 级飙到 10s 级
ABSOLUTE_CAP = 150_000          # 对应 EVOFLOW_COMPACT_ABSOLUTE_TOKENS
# 压缩后把上下文回填到目标值的 122%（多留一点，减少连续压缩次数）
POST_COMPRESS_REFILL = 1.22     # 压缩后回填到目标的 122%
# 同一轮内再次回填的放大系数：1.5 倍，避免「刚压缩完又立刻超阈值」
SAME_TURN_REFILL = 1.5


def estimate_tokens(text: str) -> int:
    """粗估：中文约 1 字 1 token，英文约 4 字符 1 token。宁可高估。"""
    if not text:
        return 0
    cjk = sum(1 for ch in text if ord(ch) > 0x2E80)
    return cjk + max(1, (len(text) - cjk) // 3)


def compact_threshold(context_length: int = DEFAULT_CONTEXT) -> int:
    """压缩触发阈值：上下文比例与绝对上限取较小值。"""
    by_ratio = int(context_length * AUTO_COMPACT_RATIO)
    return min(by_ratio, ABSOLUTE_CAP)   # 两者取小：绝对上限永远生效


def should_compact(tokens: int, context_length: int = DEFAULT_CONTEXT) -> bool:
    """当前 token 数是否达到压缩阈值。"""
    return tokens >= compact_threshold(context_length)


def refill_target(threshold: int, same_turn: bool = False) -> int:
    """压缩后的回填目标：按同轮/跨轮比例把阈值换算成可用预算。"""
    ratio = SAME_TURN_REFILL if same_turn else POST_COMPRESS_REFILL
    return int(threshold / ratio)


# 分层预算的份额：system 与工具 schema 是「必须完整」的，先留固定上限；
# 工具结果是「可裁剪」的，留一份上限；剩下全给历史对话。
SYSTEM_SHARE = 0.15
TOOL_SCHEMA_SHARE = 0.15
TOOL_RESULT_SHARE = 0.25


def layered_quotas(
    context_length: int = DEFAULT_CONTEXT,
    *,
    system_tokens: int = 0,
    tool_tokens: int = 0,
    tool_result_tokens: int = 0,
) -> dict[str, int]:
    """把压缩阈值拆成四层配额。

    system 与工具 schema 不按配额截断（截断安全声明比省 token 更危险），
    配额只用于给历史和工具结果设上限；调用方应按 ``min(实际, 配额)`` 规划。
    """
    usable = compact_threshold(context_length)
    system_quota = min(max(0, system_tokens), int(usable * SYSTEM_SHARE))
    tool_quota = min(max(0, tool_tokens), int(usable * TOOL_SCHEMA_SHARE))
    result_quota = min(max(0, tool_result_tokens), int(usable * TOOL_RESULT_SHARE))
    history_quota = max(1, usable - system_quota - tool_quota - result_quota)
    return {
        "system": system_quota,
        "tools": tool_quota,
        "tool_results": result_quota,
        "history": history_quota,
    }
