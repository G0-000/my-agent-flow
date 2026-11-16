from __future__ import annotations


def test_cap_beats_ratio():
    from myagentflow.context.budget import ABSOLUTE_CAP, compact_threshold

    assert compact_threshold(256_000) == ABSOLUTE_CAP
    assert compact_threshold(100_000) == 90_000     # 小窗口时比例生效


def test_refill():
    from myagentflow.context.budget import refill_target

    assert refill_target(150_000) < 150_000
    assert refill_target(150_000, same_turn=True) < refill_target(150_000)
