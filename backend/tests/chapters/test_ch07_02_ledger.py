"""一、文件说明
    07/02 协作账本：防双领与超时回收。

二、覆盖
    test_double_claim_and_reclaim()  旧版本号二次认领被拒；超时后回收成 open 且版本递增。

三、运行
    uv run pytest tests/chapters/test_ch07_02_ledger.py -q
"""

from __future__ import annotations

import pytest


def test_double_claim_and_reclaim():
    """旧版本号二次认领被拒；超时后回收成 open 且版本递增。"""
    from myagentflow.collab.ledger import Ledger, Task

    l = Ledger()
    l.add(Task("t1", "写"))
    l.claim("t1", "alice", 0)

    # 第二次认领带的是旧版本号 0：必须被拒（这就是防双领）
    with pytest.raises(RuntimeError):
        l.claim("t1", "bob", 0)

    # 时间不能靠 sleep 凑：把 now 显式推到「最后心跳 + 11 秒」，
    # 超过 timeout=10 才算过期，测试才是确定的
    last_seen = l._tasks["t1"].last_seen
    assert l.reclaim_stale(timeout=10, now=last_seen + 11) == ["t1"]
    assert l._tasks["t1"].status == "open"
    assert l._tasks["t1"].version == 2
