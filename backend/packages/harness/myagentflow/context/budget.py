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
