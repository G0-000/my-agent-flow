"""一、文件说明
    03/04 上下文预算：压缩阈值与回填目标。

二、覆盖
    test_cap_beats_ratio()  大窗口被绝对上限截住，小窗口按比例算。
    test_refill()           回填目标小于阈值，同轮回填比跨轮更保守。

三、运行
    uv run pytest tests/chapters/test_ch03_04_budget.py -q
"""

from __future__ import annotations


def test_cap_beats_ratio():
    """大窗口被绝对上限截住，小窗口按比例算。"""
    from myagentflow.context.budget import ABSOLUTE_CAP, compact_threshold

    assert compact_threshold(256_000) == ABSOLUTE_CAP
    assert compact_threshold(100_000) == 90_000     # 小窗口时比例生效


def test_refill():
    """回填目标小于阈值，同轮回填比跨轮更保守。"""
    from myagentflow.context.budget import refill_target

    assert refill_target(150_000) < 150_000
    assert refill_target(150_000, same_turn=True) < refill_target(150_000)
