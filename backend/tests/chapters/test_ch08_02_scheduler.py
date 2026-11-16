from __future__ import annotations


def test_cron_basics():
    from myagentflow.automation.scheduler import Scheduler, matches

    now = 1_700_000_000.0          # 固定时间，避免测试随「今天星期几」飘
    assert matches("* * * * *", now)
    s = Scheduler(last_run={})
    assert 0 < s.catch_up("a", "*/5 * * * *", now=now, limit=3) <= 3
