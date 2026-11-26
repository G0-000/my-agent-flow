"""一、文件说明
    工具执行器：把「注册表调用」包进中间件链。
    为什么不让图直接 registry.call：审计、参数改写、审批都要在同一个入口上做；
    图只认识 executor，不关心中间件有几层。

二、目录结构
    packages/harness/myagentflow/tools/
    ├── registry.py  工具声明与注册
    ├── executor.py  ← 本文件：请求对象 + 中间件链执行
    └── builtins/    内置工具

三、关键方法
    ToolCallRequest  一次工具调用的事实：tool_call、thread_id、run_id。
    ToolExecutor     执行入口：按中间件顺序包住 registry.call。
"""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from myagentflow.agents.middlewares.chain import Middleware, run_chain
from myagentflow.tools.registry import ToolRegistry


@dataclass
class ToolCallRequest:
    """一次工具调用的事实；字段名对齐中间件读取的 tool_call 结构。"""
    tool_call: dict[str, Any]
    thread_id: str = ""
    run_id: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def name(self) -> str:
        return str(self.tool_call.get("name") or "")

    @property
    def args(self) -> dict[str, Any]:
        raw = self.tool_call.get("args") or {}
        return raw if isinstance(raw, dict) else {}


class ToolExecutor:
    """工具执行入口：注册表 + 中间件链。"""

    def __init__(
        self,
        registry: ToolRegistry,
        middlewares: Iterable[Middleware] | None = None,
    ) -> None:
        self.registry = registry
        self.middlewares = list(middlewares or [])

    def schemas(self) -> list[dict[str, Any]]:
        """给模型看的工具 schema；与 registry 保持同一份事实。"""
        return self.registry.schemas()

    def execute(
        self,
        name: str,
        args: dict[str, Any] | None = None,
        *,
        thread_id: str = "",
        run_id: str = "",
        tool_call_id: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> Any:
        """执行一次工具调用；异常交给调用方处理，执行器不吞错。"""
        request = ToolCallRequest(
            tool_call={
                "name": str(name or ""),
                "args": dict(args or {}),
                "id": tool_call_id,
            },
            thread_id=thread_id,
            run_id=run_id,
            metadata=dict(metadata or {}),
        )

        def call(req: ToolCallRequest) -> Any:
            return self.registry.call(req.name, req.args)

        return run_chain(self.middlewares, request, call)
