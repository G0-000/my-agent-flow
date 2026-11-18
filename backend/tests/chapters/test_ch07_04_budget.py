"""一、文件说明
    07/04 计划预算：三档策略切换。

二、覆盖
    test_three_tiers()  剩余预算按比例切成 exhaustive / heuristic / stop。

三、运行
    uv run pytest tests/chapters/test_ch07_04_budget.py -q
"""

from __future__ import annotations


def test_three_tiers():
    """剩余预算按比例切成 exhaustive / heuristic / stop。"""
    from myagentflow.plans.router import Budget, Strategy, choose

    assert choose(Budget()) is Strategy.exhaustive
    assert choose(Budget(max_steps=10, steps_used=8)) is Strategy.heuristic
    assert choose(Budget(max_steps=10, steps_used=10)) is Strategy.stop
