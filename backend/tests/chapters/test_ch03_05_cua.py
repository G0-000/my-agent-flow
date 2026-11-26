"""第 03.5 章：Computer-Use 会话层与鉴权的最小行为测试。

覆盖：
- 动作协议：click/type/key 调到驱动，screenshot 只取画面
- 非法动作不消耗步数；超过 max_steps 拒绝
- 会话关闭后不可再操作
- API：无 token 401，配置 token 后可建会话并执行动作
"""

from __future__ import annotations

import pytest


class FakeDriver:
    name = "fake"

    def __init__(self) -> None:
        self.clicks: list[tuple[int, int]] = []
        self.typed: list[str] = []
        self.keys: list[str] = []
        self.frames = 0

    def capture(self) -> str:
        self.frames += 1
        return f"frame-{self.frames}"

    def click(self, x: int, y: int) -> None:
        self.clicks.append((x, y))

    def type_text(self, text: str) -> None:
        self.typed.append(text)

    def press_key(self, key: str) -> None:
        self.keys.append(key)


def test_actions_reach_driver():
    from myagentflow.cua.session import CuaSession

    drv = FakeDriver()
    s = CuaSession(session_id="s1", thread_id="t1", driver=drv)

    out = s.act({"type": "click", "x": 10, "y": 20})
    assert drv.clicks == [(10, 20)]
    assert out["step"] == 1 and out["frame"] == "frame-1"

    s.act({"type": "type", "text": "hello"})
    s.act({"type": "key", "key": "ENTER"})
    assert drv.typed == ["hello"] and drv.keys == ["ENTER"]


def test_invalid_action_does_not_consume_step():
    from myagentflow.cua.session import CuaError, CuaSession

    s = CuaSession(session_id="s2", thread_id="", driver=FakeDriver())
    with pytest.raises(CuaError):
        s.act({"type": "click", "x": "10", "y": 20})
    assert s.steps == 0

    with pytest.raises(CuaError):
        s.act({"type": "teleport"})


def test_step_limit_and_close():
    from myagentflow.cua.session import CuaError, CuaSession

    s = CuaSession(session_id="s3", thread_id="", driver=FakeDriver(), max_steps=2)
    s.act({"type": "screenshot"})
    s.act({"type": "screenshot"})
    with pytest.raises(CuaError):
        s.act({"type": "screenshot"})

    s.close()
    with pytest.raises(CuaError):
        s.screen()


def test_api_requires_token_and_works(monkeypatch):
    monkeypatch.delenv("MYAF_BRIDGE_TOKEN", raising=False)

    from fastapi.testclient import TestClient

    from app.gateway.main import create_app

    client = TestClient(create_app())
    assert client.post("/api/cua/sessions", json={}).status_code == 401

    monkeypatch.setenv("MYAF_BRIDGE_TOKEN", "t0ken")
    headers = {"x-bridge-token": "t0ken"}
    created = client.post("/api/cua/sessions", json={"max_steps": 3}, headers=headers)
    assert created.status_code == 200
    sid = created.json()["session_id"]

    acted = client.post(
        f"/api/cua/sessions/{sid}/act",
        json={"type": "click", "x": 1, "y": 2},
        headers=headers,
    )
    assert acted.status_code == 200 and acted.json()["step"] == 1

    bad = client.post(f"/api/cua/sessions/{sid}/act", json={"type": "nope"}, headers=headers)
    assert bad.status_code == 400

    assert client.get(f"/api/cua/sessions/{sid}/screen", headers=headers).status_code == 200
    assert client.delete(f"/api/cua/sessions/{sid}", headers=headers).status_code == 200
    assert client.get("/api/cua/sessions/missing/screen", headers=headers).status_code == 400
