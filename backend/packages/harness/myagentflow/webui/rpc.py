"""一、文件说明
    UI RPC：桌面端不需要 REST，一层方法表就够。
    错误码照 JSON-RPC 规范：
    -32601 方法不存在 / -32602 参数错误 / -32603 内部错误。
    自创错误码会让所有客户端各写一套映射。

二、目录结构
    packages/harness/myagentflow/webui/
    ├── __init__.py
    └── rpc.py  ← 本文件

三、关键方法
    Rpc  极简 RPC：按方法名注册并分发。
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Any


class Rpc:
    """极简 RPC：按方法名注册并分发。"""
    def __init__(self) -> None:
        self._methods: dict[str, Callable[..., Any]] = {}

    def method(self, name: str):
        def deco(fn: Callable[..., Any]):
            self._methods[name] = fn
            return fn
        return deco

    def call(self, req: dict[str, Any]) -> dict[str, Any]:
        rid = req.get("id")
        name = req.get("method", "")
        fn = self._methods.get(name)
        if fn is None:
            return {"id": rid, "error": {"code": -32601, "message": f"方法不存在：{name}"}}
        try:
            return {"id": rid, "result": fn(**(req.get("params") or {}))}
        except TypeError as exc:
            return {"id": rid, "error": {"code": -32602, "message": str(exc)}}
        except Exception as exc:
            return {"id": rid, "error": {"code": -32603, "message": str(exc)}}
