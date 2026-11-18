"""第 3 章 / 会话与消息仓储：两个文件各自负责，函数名与 EvoFlow 一致。"""
from __future__ import annotations


def _fresh_db(monkeypatch, tmp_path):
    """换到临时库文件并丢掉旧连接，避免测试之间串数据。"""
    from myagentflow.persistence import db

    monkeypatch.setenv("MYAF_DB_PATH", str(tmp_path / "app.sqlite"))
    db.reset_db()


def test_append_and_list(monkeypatch, tmp_path):
    from myagentflow.persistence.chat_message_repositories import (
        append_message,
        count_messages,
        list_messages,
    )

    _fresh_db(monkeypatch, tmp_path)
    assert append_message("a", "user", "1") == 1
    assert append_message("a", "assistant", "2") == 2
    assert append_message("b", "user", "x") == 1          # 另一个会话从 1 开始

    assert [m["content"] for m in list_messages("a")] == ["1", "2"]
    assert [m["content"] for m in list_messages("a", limit=1)] == ["2"]   # 取最近一条
    assert count_messages("a") == 2


def test_delete_messages_for_session(monkeypatch, tmp_path):
    from myagentflow.persistence.chat_message_repositories import (
        append_message,
        delete_messages_for_session,
    )

    _fresh_db(monkeypatch, tmp_path)
    append_message("a", "user", "1")
    append_message("a", "assistant", "2")
    assert delete_messages_for_session("a") == 2
    assert delete_messages_for_session("a") == 0


def test_session_row_lifecycle(monkeypatch, tmp_path):
    from myagentflow.persistence.session_repositories import (
        delete_sessions_by_thread_id,
        get_session_row_for_ui,
        list_sessions_for_ui,
        upsert_session_row,
    )

    _fresh_db(monkeypatch, tmp_path)
    upsert_session_row("s1", title="第一条")
    upsert_session_row("s2")
    upsert_session_row("s1")                              # 再 upsert 只刷新时间，标题保留

    row = get_session_row_for_ui("s1")
    assert row is not None and row["title"] == "第一条"
    assert [r["session_key"] for r in list_sessions_for_ui()] == ["s1", "s2"]

    assert delete_sessions_by_thread_id("s1") == 1
    assert get_session_row_for_ui("s1") is None
