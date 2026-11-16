from __future__ import annotations


def test_stop_and_resume():
    from myagentflow.plans.workflow import Workflow

    calls = []
    w = Workflow("w", [
        ("a", lambda: calls.append("a") or 1),
        ("b", lambda: 1 / 0),
        ("c", lambda: calls.append("c") or 3),
    ])
    w.run()
    assert calls == ["a"]                 # c 没执行
    assert w.history[-1].ok is False

    w.steps[1] = ("b", lambda: calls.append("b") or 2)
    w.resume_from(1)
    assert calls == ["a", "b", "c"]
