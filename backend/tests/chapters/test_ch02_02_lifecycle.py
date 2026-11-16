from __future__ import annotations

import pytest


def test_one_active_run_per_thread():
    from myagentflow.session_execution.lifecycle import RunRegistry

    reg = RunRegistry()
    r1 = reg.start("t1")
    with pytest.raises(RuntimeError):
        reg.start("t1")
    reg.finish(r1.run_id)
    reg.start("t1")            # 收尾后可以再开


def test_cancel_wins_over_finish():
    from myagentflow.session_execution.lifecycle import RunRegistry

    reg = RunRegistry()
    r = reg.start("t2")
    assert reg.cancel(r.run_id) is True
    reg.finish(r.run_id, "finished")
    assert reg._runs[r.run_id].status == "cancelled"
