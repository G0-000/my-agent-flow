"""04.4：分享 HTTP 路由、快照隔离、导出脱敏与批量吊销。"""

from __future__ import annotations


def _prepare(monkeypatch, tmp_path):
    monkeypatch.setenv("MYAF_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("MYAF_DB_PATH", str(tmp_path / "chat.sqlite"))

    from myagentflow.persistence import db

    from app.gateway.routers.shares import reset_share_store

    db.reset_db()
    reset_share_store()


def _seed(thread_id: str, rows: list[tuple[str, str]]) -> None:
    from myagentflow.persistence.chat_message_repositories import append_message
    from myagentflow.persistence.session_repositories import upsert_session_row

    upsert_session_row(thread_id, title="分享测试")
    for role, content in rows:
        append_message(thread_id, role, content)


def test_share_snapshot_isolated_from_later_messages(monkeypatch, tmp_path):
    _prepare(monkeypatch, tmp_path)
    _seed("t-share", [("user", "第一问"), ("assistant", "第一答")])

    from fastapi.testclient import TestClient

    from app.gateway.main import create_app

    client = TestClient(create_app())
    created = client.post("/api/shares", json={"thread_id": "t-share"}).json()
    token = created["token"]
    assert created["count"] == 2

    from myagentflow.persistence.chat_message_repositories import append_message

    append_message("t-share", "user", "分享之后的新消息")

    view = client.get(f"/api/shares/{token}").json()
    assert view["snapshot"] is True
    assert [m["content"] for m in view["messages"]] == ["第一问", "第一答"]

    missing = client.get("/api/shares/not-a-token")
    assert missing.status_code == 404

    from myagentflow.persistence import db

    from app.gateway.routers.shares import reset_share_store

    db.reset_db()
    reset_share_store()


def test_export_redacts_secrets_and_home_paths(monkeypatch, tmp_path):
    _prepare(monkeypatch, tmp_path)
    _seed(
        "t-redact",
        [
            ("user", "key 是 sk-abcdef123456，路径 /Users/alice/project"),
            ("assistant", "password= hunter2 已收到"),
        ],
    )

    from fastapi.testclient import TestClient

    from app.gateway.main import create_app

    client = TestClient(create_app())
    token = client.post("/api/shares", json={"thread_id": "t-redact"}).json()["token"]

    markdown = client.get(f"/api/shares/{token}/export", params={"format": "markdown"})
    assert markdown.status_code == 200
    assert "sk-abcdef123456" not in markdown.text
    assert "/Users/alice" not in markdown.text
    assert "hunter2" not in markdown.text

    as_json = client.get(f"/api/shares/{token}/export", params={"format": "json"}).json()
    assert as_json["thread_id"] == "t-redact"
    assert "sk-abcdef123456" not in as_json["messages"][0]["content"]

    from myagentflow.persistence import db

    from app.gateway.routers.shares import reset_share_store

    db.reset_db()
    reset_share_store()


def test_revoke_single_and_by_thread(monkeypatch, tmp_path):
    _prepare(monkeypatch, tmp_path)
    _seed("t-rev", [("user", "hi"), ("assistant", "hello")])

    from fastapi.testclient import TestClient

    from app.gateway.main import create_app

    client = TestClient(create_app())
    first = client.post("/api/shares", json={"thread_id": "t-rev"}).json()["token"]
    second = client.post("/api/shares", json={"thread_id": "t-rev"}).json()["token"]

    assert client.delete(f"/api/shares/{first}").json()["revoked"] is True
    assert client.get(f"/api/shares/{first}").status_code == 410

    bulk = client.delete("/api/shares/thread/t-rev").json()
    assert bulk["revoked"] == 1
    assert client.get(f"/api/shares/{second}").status_code == 410

    from myagentflow.persistence import db

    from app.gateway.routers.shares import reset_share_store

    db.reset_db()
    reset_share_store()
