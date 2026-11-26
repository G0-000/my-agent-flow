"""第 03.2 章：工具执行器与中间件链的最小行为测试。"""

from __future__ import annotations

import pytest
from myagentflow.agents.middlewares.chain import Middleware
from myagentflow.tools.builtins.echo import register_echo
from myagentflow.tools.executor import ToolExecutor
from myagentflow.tools.registry import ToolRegistry


class Recorder(Middleware):
    """记录进入/退出顺序，并改写一次参数。"""

    def __init__(self) -> None:
        self.order: list[str] = []

    def wrap_tool_call(self, request, handler):
        self.order.append("before")
        request.tool_call["args"]["text"] = "rewritten"
        result = handler(request)
        self.order.append("after")
        return result


def test_executor_runs_middleware_and_tool():
    registry = ToolRegistry()
    register_echo(registry)
    recorder = Recorder()
    executor = ToolExecutor(registry, [recorder])

    result = executor.execute("echo", {"text": "original"}, tool_call_id="c1")

    assert result == "rewritten"
    assert recorder.order == ["before", "after"]


def test_executor_does_not_swallow_errors():
    executor = ToolExecutor(ToolRegistry(), [])

    with pytest.raises(KeyError):
        executor.execute("missing", {})
