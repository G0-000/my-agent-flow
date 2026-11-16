from __future__ import annotations


def test_history_and_disable(tmp_path):
    from myagentflow.automation.store import AutomationStore

    s = AutomationStore(tmp_path / "a.sqlite")
    a = s.add("日报", "0 9 * * *", "总结")
    r = s.begin_run(a); s.finish_run(r, "ok")
    assert s._conn.execute("SELECT status FROM runs WHERE id=?", (r,)).fetchone()[0] == "ok"

    s._conn.execute("UPDATE automations SET enabled=0 WHERE id=?", (a,)); s._conn.commit()
    assert s.enabled() == []
