"""03.6 / 03.7：MCP 配置装配与「外部工具默认需审批」。"""

from __future__ import annotations

import json

import pytest


class FakeMcpClient:
    def __init__(self, command: list[str]):
        self.command = command
        self.closed = False

    def initialize(self) -> dict:
        return {}

    def list_tools(self) -> list[dict]:
        return [
            {
                "name": "read_file",
                "description": "读文件",
                "inputSchema": {"type": "object", "properties": {"path": {"type": "string"}}},
            }
        ]

    def call_tool(self, name: str, args: dict) -> dict:
        return {"content": [{"type": "text", "text": f"{name}:{args.get('path')}"}]}

    def close(self) -> None:
        self.closed = True


def test_parse_specs_skips_bad_entries():
    from myagentflow.mcp.assembly import parse_server_specs

    assert parse_server_specs("not json") == []
    assert parse_server_specs(json.dumps({"name": "x"})) == []
    specs = parse_server_specs(
        json.dumps(
            [
                {"name": "fs", "command": ["echo"]},
                {"name": "bad"},
            ]
        )
    )
    assert len(specs) == 1
    assert specs[0]["prefix"] == "mcp__fs__"


def test_register_configured_tools(monkeypatch):
    from myagentflow.mcp.assembly import register_configured_mcp_tools, reset_clients
    from myagentflow.tools.registry import ToolRegistry

    monkeypatch.setenv(
        "MYAF_MCP_SERVERS",
        json.dumps([{"name": "fs", "command": ["fake"]}]),
    )
    registry = ToolRegistry()
    names = register_configured_mcp_tools(registry, client_factory=FakeMcpClient)

    assert names == ["mcp__fs__read_file"]
    assert registry.call("mcp__fs__read_file", {"path": "a.md"}) == "read_file:a.md"
    reset_clients()


def test_mcp_tool_requires_approval_by_default():
    from myagentflow.agents.middlewares.policy import ApprovalRequired, PolicyMiddleware
    from myagentflow.sandbox.approvals import ApprovalStore
    from myagentflow.tools.executor import ToolCallRequest

    store = ApprovalStore()
    middleware = PolicyMiddleware(store)
    request = ToolCallRequest(
        tool_call={"name": "mcp__fs__read_file", "args": {"path": "a.md"}, "id": "c1"},
        run_id="run-1",
    )

    with pytest.raises(ApprovalRequired) as exc:
        middleware.wrap_tool_call(request, lambda r: "ok")

    approval_id = exc.value.approval_id
    store.resolve(approval_id, "approved")
    request.metadata = {"approval_id": approval_id}
    assert middleware.wrap_tool_call(request, lambda r: "ok") == "ok"


def test_mcp_tool_allowed_by_env(monkeypatch):
    from myagentflow.agents.middlewares.policy import PolicyMiddleware
    from myagentflow.sandbox.approvals import ApprovalStore
    from myagentflow.tools.executor import ToolCallRequest

    monkeypatch.setenv("MYAF_MCP_ALLOW", "mcp__fs__read_file")
    middleware = PolicyMiddleware(ApprovalStore())
    request = ToolCallRequest(tool_call={"name": "mcp__fs__read_file", "args": {}, "id": "c1"})
    assert middleware.wrap_tool_call(request, lambda r: "ok") == "ok"
