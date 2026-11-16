from __future__ import annotations


def test_idempotent():
    from myagentflow.session_execution.idempotency import Idempotency

    i = Idempotency()
    assert i.begin("k")[0] == "fresh"
    assert i.begin("k")[0] == "running"
    i.finish("k", {"ok": True})
    status, result = i.begin("k")
    assert status == "cached" and result == {"ok": True}
