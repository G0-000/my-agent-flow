"""一、文件说明
    08/03 心跳：状态去重与每小时上限。

二、覆盖
    test_heartbeat()  状态没变不重复跑，总次数不超过每小时上限。

三、运行
    uv run pytest tests/chapters/test_ch08_03_heartbeat.py -q
"""

from __future__ import annotations


def test_heartbeat():
    """状态没变不重复跑，总次数不超过每小时上限。"""
    from myagentflow.automation.heartbeat import Heartbeat

    h = Heartbeat(max_per_hour=6)
    assert h.should_run({"a": "1"}) is True
    assert h.should_run({"a": "1"}) is False
    for i in range(10):
        h.should_run({"a": str(i)})       # 前 5 次通过，之后被节流
    assert len(h._events) <= 6
