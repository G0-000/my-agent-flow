"""一、文件说明
    08/01 自动化存储：运行记录落库与停用过滤。

二、覆盖
    test_history_and_disable()  运行结果落库；停用的自动化不再出现在 enabled()。

三、运行
    uv run pytest tests/chapters/test_ch08_01_automation.py -q
"""

from __future__ import annotations


def test_history_and_disable(tmp_path):
    """运行结果落库；停用的自动化不再出现在 enabled()。"""
    from myagentflow.automation.store import AutomationStore

    s = AutomationStore(tmp_path / "a.sqlite")
    a = s.add("日报", "0 9 * * *", "总结")
    r = s.begin_run(a); s.finish_run(r, "ok")
    assert s._conn.execute("SELECT status FROM runs WHERE id=?", (r,)).fetchone()[0] == "ok"

    s._conn.execute("UPDATE automations SET enabled=0 WHERE id=?", (a,)); s._conn.commit()
    assert s.enabled() == []
