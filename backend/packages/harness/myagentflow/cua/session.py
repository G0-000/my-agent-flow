"""一、文件说明
    Computer-Use 的会话层：动作协议、步数上限、动作日志。
    为什么把驱动抽出来：截图/点击依赖具体平台（macOS、Windows、浏览器），
    会话层只负责“动作合法性 + 状态”，换平台只换驱动，不动协议。

二、目录结构
    packages/harness/myagentflow/cua/
    ├── __init__.py
    └── session.py  ← 本文件

三、关键方法
    CuaDriver  驱动协议：capture/click/type_text/press_key
    CuaSession.act()  校验动作 → 计数 → 调驱动 → 返回观察结果
    CuaRegistry       会话注册：create/get/close，按 thread 绑定
"""
from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from typing import Any, Protocol

ACTION_TYPES = {"screenshot", "click", "type", "key"}


class CuaDriver(Protocol):
    """平台驱动契约；实现方只关心“怎么做”，不关心协议。"""

    name: str

    def capture(self) -> str: ...

    def click(self, x: int, y: int) -> None: ...

    def type_text(self, text: str) -> None: ...

    def press_key(self, key: str) -> None: ...


class CuaError(RuntimeError):
    """动作非法、步数超限、会话不存在，都走同一个错误类型。"""


@dataclass
class CuaSession:
    """一次 Computer-Use 会话：驱动 + 步数 + 动作日志。"""

    session_id: str
    thread_id: str
    driver: CuaDriver
    max_steps: int = 20
    steps: int = 0
    closed: bool = False
    log: list[dict[str, Any]] = field(default_factory=list)

    def _check_open(self) -> None:
        if self.closed:
            raise CuaError("会话已关闭")
        if self.steps >= self.max_steps:
            raise CuaError(f"超过步数上限 {self.max_steps}")

    def act(self, action: dict[str, Any]) -> dict[str, Any]:
        """执行一个动作；先校验再执行，非法动作不消耗步数。"""
        self._check_open()
        kind = str(action.get("type") or "").strip().lower()
        if kind not in ACTION_TYPES:
            raise CuaError(f"未知动作：{kind}")

        if kind == "click":
            x, y = action.get("x"), action.get("y")
            if not isinstance(x, int) or not isinstance(y, int):
                raise CuaError("click 需要整数 x/y")
            self.driver.click(x, y)
        elif kind == "type":
            text = action.get("text")
            if not isinstance(text, str) or not text:
                raise CuaError("type 需要非空 text")
            self.driver.type_text(text)
        elif kind == "key":
            key = action.get("key")
            if not isinstance(key, str) or not key:
                raise CuaError("key 需要非空 key")
            self.driver.press_key(key)
        # screenshot 不调动作接口，统一在下面取观察结果

        self.steps += 1
        frame = self.driver.capture()
        record = {"type": kind, "step": self.steps, "frame": frame}
        self.log.append(record)
        return {"ok": True, "step": self.steps, "remaining": self.max_steps - self.steps, "frame": frame}

    def screen(self) -> dict[str, Any]:
        self._check_open()
        return {"session_id": self.session_id, "step": self.steps, "frame": self.driver.capture()}

    def close(self) -> None:
        self.closed = True


class CuaRegistry:
    """进程内会话注册；跨进程要换成持久化 + 驱动租约。"""

    def __init__(self) -> None:
        self._sessions: dict[str, CuaSession] = {}
        self._lock = threading.Lock()

    def create(
        self,
        driver: CuaDriver,
        *,
        thread_id: str = "",
        max_steps: int = 20,
    ) -> CuaSession:
        sid = f"cua-{uuid.uuid4().hex[:12]}"
        session = CuaSession(
            session_id=sid,
            thread_id=thread_id,
            driver=driver,
            max_steps=max(1, int(max_steps)),
        )
        with self._lock:
            self._sessions[sid] = session
        return session

    def get(self, session_id: str) -> CuaSession:
        with self._lock:
            session = self._sessions.get(session_id)
        if session is None:
            raise CuaError(f"会话不存在：{session_id}")
        return session

    def close(self, session_id: str) -> None:
        session = self.get(session_id)
        session.close()
        with self._lock:
            self._sessions.pop(session_id, None)

    def count(self) -> int:
        with self._lock:
            return len(self._sessions)


_REGISTRY = CuaRegistry()


def get_cua_registry() -> CuaRegistry:
    return _REGISTRY
