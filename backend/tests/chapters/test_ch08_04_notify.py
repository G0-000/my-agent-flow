from __future__ import annotations


def test_dedup_and_isolation():
    from myagentflow.automation.notify import Notifier

    n = Notifier({"desktop": lambda t: True, "webhook": lambda t: 1 / 0})
    first = n.send("all", "完成", dedup_key="r1")
    assert first["desktop"] == "sent" and first["webhook"] == "failed"
    second = n.send("all", "完成", dedup_key="r1")
    assert second["desktop"] == "skipped"
