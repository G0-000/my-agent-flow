"""一、文件说明
    06/03 审批：终态不可改、按 run 取消。

二、覆盖
    test_terminal_and_cancel()  审批终态不可再改，取消按 run 生效。

三、运行
    uv run pytest tests/chapters/test_ch06_03_approvals.py -q
"""

from __future__ import annotations

import pytest


def test_terminal_and_cancel():
    """审批终态不可再改，取消按 run 生效。"""
    from myagentflow.sandbox.approvals import ApprovalStore

    s = ApprovalStore()
    a = s.create("r1", "bash", {})
    s.resolve(a.id, "approved")
    with pytest.raises(RuntimeError):
        s.resolve(a.id, "rejected")

    b = s.create("r2", "bash", {})
    assert s.cancel_run("r2") == 1
    assert b.status == "cancelled"
