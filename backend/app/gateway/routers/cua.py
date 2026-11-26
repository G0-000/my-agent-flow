"""Computer-Use API：建会话、执行动作、取当前画面。

鉴权：所有 CUA 路由都要 `x-bridge-token`，且环境变量 `MYAF_BRIDGE_TOKEN` 必须配置。
当前只接 NullDriver（记录动作、返回占位画面）；真实截图/点击驱动按平台另接。
"""
from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

router = APIRouter()


class NullDriver:
    """占位驱动：不碰真实桌面，只记录动作并返回固定画面标记。"""

    name = "null"

    def __init__(self) -> None:
        self.actions: list[tuple[str, object]] = []

    def capture(self) -> str:
        return f"null-frame:{len(self.actions)}"

    def click(self, x: int, y: int) -> None:
        self.actions.append(("click", (x, y)))

    def type_text(self, text: str) -> None:
        self.actions.append(("type", text))

    def press_key(self, key: str) -> None:
        self.actions.append(("key", key))


class SessionIn(BaseModel):
    thread_id: str = ""
    max_steps: int = 20


class ActionIn(BaseModel):
    type: str
    x: int | None = None
    y: int | None = None
    text: str | None = None
    key: str | None = None


def _auth(token: str | None) -> None:
    from myagentflow.tools.host_direct.bridge_auth import verify_bridge_token

    if not verify_bridge_token(token):
        raise HTTPException(status_code=401, detail="CUA 需要有效 bridge token")


def _registry():
    from myagentflow.cua.session import get_cua_registry

    return get_cua_registry()


@router.post("/cua/sessions")
def create_session(body: SessionIn, x_bridge_token: str | None = Header(default=None)) -> dict:
    _auth(x_bridge_token)
    session = _registry().create(NullDriver(), thread_id=body.thread_id, max_steps=body.max_steps)
    return {"session_id": session.session_id, "max_steps": session.max_steps}


@router.post("/cua/sessions/{session_id}/act")
def act(session_id: str, body: ActionIn, x_bridge_token: str | None = Header(default=None)) -> dict:
    _auth(x_bridge_token)
    from myagentflow.cua.session import CuaError

    try:
        return _registry().get(session_id).act(body.model_dump(exclude_none=True))
    except CuaError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/cua/sessions/{session_id}/screen")
def screen(session_id: str, x_bridge_token: str | None = Header(default=None)) -> dict:
    _auth(x_bridge_token)
    from myagentflow.cua.session import CuaError

    try:
        return _registry().get(session_id).screen()
    except CuaError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/cua/sessions/{session_id}")
def close(session_id: str, x_bridge_token: str | None = Header(default=None)) -> dict:
    _auth(x_bridge_token)
    from myagentflow.cua.session import CuaError

    try:
        _registry().close(session_id)
    except CuaError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"ok": True}
