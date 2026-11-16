from __future__ import annotations


def test_heartbeat():
    from myagentflow.automation.heartbeat import Heartbeat

    h = Heartbeat(max_per_hour=6)
    assert h.should_run({"a": "1"}) is True
    assert h.should_run({"a": "1"}) is False
    for i in range(10):
        h.should_run({"a": str(i)})       # 前 5 次通过，之后被节流
    assert len(h._events) <= 6
