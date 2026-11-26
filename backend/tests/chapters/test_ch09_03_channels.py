"""第 09.3 章：飞书渠道最小闭环。

覆盖：
- url_verification 原样回 challenge
- 配了 token 时校验失败 401
- 文本事件 → 总线 → 回复 → 渠道 send（thread 为 feishu:chat）
- 同一 event_id 重复推送只回答一次
- 非文本事件忽略；@ 提及被剥掉
- FeishuApi：token 缓存 + 发消息 payload 正确
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from app.channels.base import Channel


class FakeChannel(Channel):
    name = "feishu"

    def __init__(self) -> None:
        self.sent: list[tuple[str, str]] = []

    def send(self, thread_id: str, text: str) -> None:
        self.sent.append((thread_id, text))


def _event(text: str = "你好", *, event_id: str = "ev-1", message_type: str = "text") -> dict:
    return {
        "header": {"event_id": event_id, "event_type": "im.message.receive_v1", "token": "t"},
        "event": {
            "message": {
                "message_id": "om-1",
                "chat_id": "oc_1",
                "message_type": message_type,
                "content": json.dumps({"text": text}, ensure_ascii=False),
            },
            "sender": {"sender_id": {"open_id": "ou_1"}},
        },
    }


@pytest.fixture()
def client(monkeypatch):
    from app.channels.message_bus import MessageBus
    from app.channels.service import ChannelService
    from app.gateway.main import create_app
    from app.gateway.routers.channels import (
        install_channel_service,
        reset_channel_service,
    )

    monkeypatch.delenv("FEISHU_VERIFICATION_TOKEN", raising=False)
    monkeypatch.delenv("FEISHU_APP_ID", raising=False)
    monkeypatch.delenv("FEISHU_APP_SECRET", raising=False)
    reset_channel_service()

    ch = FakeChannel()
    bus = MessageBus()
    bus.register(ch)
    bus.set_handler(lambda msg: f"echo:{msg.text}:{msg.thread_id}")
    install_channel_service(ChannelService(bus))

    app = create_app()
    with TestClient(app) as c:
        yield c, ch
    reset_channel_service()


def test_url_verification(client):
    c, _ = client
    r = c.post("/api/channels/feishu/events", json={"type": "url_verification", "challenge": "abc"})
    assert r.status_code == 200
    assert r.json() == {"challenge": "abc"}


def test_text_event_to_channel_send(client):
    c, ch = client
    r = c.post("/api/channels/feishu/events", json=_event("你好"))
    assert r.status_code == 200
    assert r.json()["ok"] is True
    assert ch.sent == [("feishu:oc_1", "echo:你好:feishu:oc_1")]


def test_duplicate_event_answered_once(client):
    c, ch = client
    payload = _event("重复", event_id="ev-dup")
    assert c.post("/api/channels/feishu/events", json=payload).json()["ok"] is True
    assert c.post("/api/channels/feishu/events", json=payload).json()["ignored"] == "duplicate"
    assert len(ch.sent) == 1


def test_non_text_ignored(client):
    c, ch = client
    r = c.post("/api/channels/feishu/events", json=_event("x", message_type="image"))
    assert r.json()["ignored"] == "non_text"
    assert ch.sent == []


def test_mention_stripped(client):
    c, ch = client
    payload = _event("@_user_123 帮我总结")
    c.post("/api/channels/feishu/events", json=payload)
    assert ch.sent[0][1].startswith("echo:帮我总结")


def test_token_mismatch_401(client, monkeypatch):
    c, ch = client
    monkeypatch.setenv("FEISHU_VERIFICATION_TOKEN", "expected")
    r = c.post("/api/channels/feishu/events", json=_event("x", event_id="ev-token"))
    assert r.status_code == 401
    assert ch.sent == []


def test_feishu_api_token_cache_and_payload():
    from app.channels.feishu import FeishuApi

    calls: list[tuple[str, dict, dict]] = []

    def fake_post(url, payload, headers):
        calls.append((url, payload, headers))
        if "tenant_access_token" in url:
            return {"code": 0, "tenant_access_token": "tok", "expire": 7200}
        return {"code": 0, "data": {"message_id": "om-x"}}

    api = FeishuApi(app_id="a", app_secret="b", http_post=fake_post)
    api.send_text("oc_1", "hi", now=100.0)
    api.send_text("oc_1", "hi2", now=101.0)
    assert len(calls) == 3  # 一次 token + 两次发消息
    url, payload, headers = calls[1]
    assert "receive_id_type=chat_id" in url
    assert payload["receive_id"] == "oc_1"
    assert payload["msg_type"] == "text"
    assert json.loads(payload["content"]) == {"text": "hi"}
    assert headers["Authorization"] == "Bearer tok"
