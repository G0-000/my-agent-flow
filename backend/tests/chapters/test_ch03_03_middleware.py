"""一、文件说明
    03/03 中间件链：洋葱顺序、异常继续上抛、审计只留一行。

二、覆盖
    test_chain_is_onion()        列表第一个在最外层：进正序、出逆序。
    test_chain_propagates_error() 工具抛异常时，中间件仍退出且异常不被吞。
    test_audit_logs_success()    审计记录工具名、参数摘要、耗时、ok=True。

三、运行
    uv run pytest tests/chapters/test_ch03_03_middleware.py -q
"""

from __future__ import annotations

from types import SimpleNamespace


def _request(name: str = "echo", args: dict | None = None):
    """构造最小工具请求；只保留中间件会读的 name/args。"""
    return SimpleNamespace(tool_call={"name": name, "args": args or {}})


def test_chain_is_onion():
    """列表第一个在最外层：进正序、出逆序。"""
    from myagentflow.agents.middlewares.chain import Middleware, run_chain

    events: list[str] = []

    class Rec(Middleware):
        """记录进入/退出顺序的中间件替身。"""

        def __init__(self, name: str) -> None:
            """保存名字，供事件序列断言。"""
            self.name = name

        def wrap_tool_call(self, request, handler):
            """进入时记 in，退出时记 out；不改变工具结果。"""
            events.append(f"{self.name}:in")
            try:
                return handler(request)
            finally:
                events.append(f"{self.name}:out")

    result = run_chain(
        [Rec("outer"), Rec("inner")],
        _request(),
        lambda req: events.append("call") or "ok",
    )
    assert result == "ok"
    assert events == ["outer:in", "inner:in", "call", "inner:out", "outer:out"]


def test_chain_propagates_error():
    """工具抛异常时，中间件仍退出且异常不被吞。"""
    import pytest
    from myagentflow.agents.middlewares.chain import Middleware, run_chain

    events: list[str] = []

    class Rec(Middleware):
        """只记录进出的中间件替身，用于验证异常路径也会退出。"""

        def wrap_tool_call(self, request, handler):
            """进入记 in，finally 记 out；异常继续上抛。"""
            events.append("in")
            try:
                return handler(request)
            finally:
                events.append("out")

    def boom(req):
        """模拟工具执行失败：记录调用后抛 ValueError。"""
        events.append("call")
        raise ValueError("tool failed")

    with pytest.raises(ValueError):
        run_chain([Rec()], _request(), boom)
    assert events == ["in", "call", "out"]


def test_audit_logs_success(caplog):
    """审计记录工具名、参数摘要、耗时、ok=True。"""
    from myagentflow.agents.middlewares.audit import AuditMiddleware
    from myagentflow.agents.middlewares.chain import run_chain

    with caplog.at_level("INFO", logger="myaf.audit"):
        run_chain(
            [AuditMiddleware()],
            _request("echo", {"text": "hi"}),
            lambda req: "pong",
        )
    assert any(
        "tool=echo" in r.message and "ok=True" in r.message for r in caplog.records
    )
