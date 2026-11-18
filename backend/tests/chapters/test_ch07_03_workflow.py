"""一、文件说明
    07/03 工作流：失败即停、从失败步续跑。

二、覆盖
    test_stop_and_resume()  中间步骤抛错即停；替换该步后可从失败处续跑到结束。

三、运行
    uv run pytest tests/chapters/test_ch07_03_workflow.py -q
"""

from __future__ import annotations


def test_stop_and_resume():
    """中间步骤抛错即停；替换该步后可从失败处续跑到结束。"""
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
