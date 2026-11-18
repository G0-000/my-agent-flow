"""一、文件说明
    08/02 调度：cron 命中与补跑上限。

二、覆盖
    test_cron_basics()  通配 cron 命中；*/5 补跑次数不超过 limit。

三、运行
    uv run pytest tests/chapters/test_ch08_02_scheduler.py -q
"""

from __future__ import annotations


def test_cron_basics():
    """通配 cron 命中；*/5 补跑次数不超过 limit。"""
    from myagentflow.automation.scheduler import Scheduler, matches

    now = 1_700_000_000.0          # 固定时间，避免测试随「今天星期几」飘
    assert matches("* * * * *", now)
    s = Scheduler(last_run={})
    assert 0 < s.catch_up("a", "*/5 * * * *", now=now, limit=3) <= 3
