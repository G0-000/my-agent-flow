"""一、文件说明
    11/05 评测：通过率与异常隔离。

二、覆盖
    test_eval()  通过率按用例算；模型异常记 error 而不是整体崩。

三、运行
    uv run pytest tests/chapters/test_ch11_05_eval.py -q
"""

from __future__ import annotations


def test_eval():
    """通过率按用例算；模型异常记 error 而不是整体崩。"""
    from myagentflow.eval.runner import Case, run

    cases = [Case("a", "x", ("你好",)), Case("b", "y", ("再见",))]
    report = run(cases, lambda p: "你好")
    assert report["passed"] == 1 and report["rate"] == 0.5

    def boom(_p):
        raise RuntimeError("model down")

    report = run(cases, boom)
    assert report["passed"] == 0 and all("error" in r for r in report["results"])
