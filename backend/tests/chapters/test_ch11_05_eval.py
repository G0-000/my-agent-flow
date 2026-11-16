from __future__ import annotations


def test_eval():
    from myagentflow.eval.runner import Case, run

    cases = [Case("a", "x", ("你好",)), Case("b", "y", ("再见",))]
    report = run(cases, lambda p: "你好")
    assert report["passed"] == 1 and report["rate"] == 0.5

    def boom(_p):
        raise RuntimeError("model down")

    report = run(cases, boom)
    assert report["passed"] == 0 and all("error" in r for r in report["results"])
