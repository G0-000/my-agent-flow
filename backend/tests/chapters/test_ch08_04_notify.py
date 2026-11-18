"""一、文件说明
    08/04 通知：渠道隔离与 dedup。

二、覆盖
    test_dedup_and_isolation()  单渠道异常不影响其他渠道；同 dedup_key 第二次跳过。

三、运行
    uv run pytest tests/chapters/test_ch08_04_notify.py -q
"""

from __future__ import annotations


def test_dedup_and_isolation():
    """单渠道异常不影响其他渠道；同 dedup_key 第二次跳过。"""
    from myagentflow.automation.notify import Notifier

    n = Notifier({"desktop": lambda t: True, "webhook": lambda t: 1 / 0})
    first = n.send("all", "完成", dedup_key="r1")
    assert first["desktop"] == "sent" and first["webhook"] == "failed"
    second = n.send("all", "完成", dedup_key="r1")
    assert second["desktop"] == "skipped"
