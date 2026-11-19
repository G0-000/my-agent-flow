"""一、文件说明
    02/02 run 生命周期：线程内单活、取消优先。

二、覆盖
    test_one_active_run_per_thread()  同线程第二次 start 抛 RuntimeError，finish 后可再开。
    test_cancel_wins_over_finish()    cancel 后即使再 finish，状态仍是 cancelled。
    test_cancel_is_per_run()          取消只影响目标 run，不误伤别的线程。
    test_cancel_unknown_and_done()    取消不存在/已收尾的 run 返回 False，不抛异常。

三、运行
    uv run pytest tests/chapters/test_ch02_02_lifecycle.py -q
"""

from __future__ import annotations

import pytest


def test_one_active_run_per_thread():
    """同线程第二次 start 抛 RuntimeError，finish 后可再开。"""
    from myagentflow.session_execution.lifecycle import RunRegistry

    reg = RunRegistry()
    r1 = reg.start("t1")
    with pytest.raises(RuntimeError):
        reg.start("t1")
    reg.finish(r1.run_id)
    reg.start("t1")            # 收尾后可以再开


def test_cancel_wins_over_finish():
    """cancel 后即使再 finish，状态仍是 cancelled。"""
    from myagentflow.session_execution.lifecycle import RunRegistry

    reg = RunRegistry()
    r = reg.start("t2")
    assert reg.cancel(r.run_id) is True
    reg.finish(r.run_id, "finished")
    assert reg._runs[r.run_id].status == "cancelled"


def test_cancel_is_per_run():
    """取消只影响目标 run：另一个线程的 run 仍然能正常收尾。"""
    from myagentflow.session_execution.lifecycle import RunRegistry

    reg = RunRegistry()
    r1 = reg.start("t1")
    r2 = reg.start("t2")
    assert reg.cancel(r1.run_id) is True
    assert reg.is_cancelled(r1.run_id) is True
    assert reg.is_cancelled(r2.run_id) is False
    reg.finish(r2.run_id)
    assert reg._runs[r2.run_id].status == "finished"


def test_cancel_unknown_and_done():
    """取消不存在的 run 或已收尾的 run 都返回 False。"""
    from myagentflow.session_execution.lifecycle import RunRegistry

    reg = RunRegistry()
    assert reg.cancel("no-such-run") is False
    r = reg.start("t3")
    reg.finish(r.run_id)
    assert reg.cancel(r.run_id) is False
