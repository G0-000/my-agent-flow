"""一、文件说明
    07/05 幂等：fresh / running / cached 三态。

二、覆盖
    test_idempotent()  同 key 首次 fresh、执行中 running、完成后 cached 带结果。

三、运行
    uv run pytest tests/chapters/test_ch07_05_idempotency.py -q
"""

from __future__ import annotations


def test_idempotent():
    """同 key 首次 fresh、执行中 running、完成后 cached 带结果。"""
    from myagentflow.session_execution.idempotency import Idempotency

    i = Idempotency()
    assert i.begin("k")[0] == "fresh"
    assert i.begin("k")[0] == "running"
    i.finish("k", {"ok": True})
    status, result = i.begin("k")
    assert status == "cached" and result == {"ok": True}
