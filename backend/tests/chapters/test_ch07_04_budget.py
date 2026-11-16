from __future__ import annotations


def test_three_tiers():
    from myagentflow.plans.router import Budget, Strategy, choose

    assert choose(Budget()) is Strategy.exhaustive
    assert choose(Budget(max_steps=10, steps_used=8)) is Strategy.heuristic
    assert choose(Budget(max_steps=10, steps_used=10)) is Strategy.stop
