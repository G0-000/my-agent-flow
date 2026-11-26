"""03.6 / 03.7：MCP 配置装配（config.yaml 的 mcp 段）与「外部工具默认需审批」。"""

from __future__ import annotations

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
    from myagentflow.config.mcp_config import McpConfig
    from myagentflow.mcp.assembly import parse_server_specs

    # 缺 command 的条目直接跳过，不让启动失败；前缀缺省 mcp__<name>__
    specs = parse_server_specs(
        McpConfig(servers=[{"name": "fs", "command": ["echo"]}, {"name": "bad"}])
    )
    assert len(specs) == 1
    assert specs[0]["prefix"] == "mcp__fs__"

    # 没配 mcp.servers → 空列表，不启动任何子进程
    assert parse_server_specs(McpConfig()) == []


def test_register_configured_tools():
    from myagentflow.config.mcp_config import McpConfig
    from myagentflow.mcp.assembly import register_configured_mcp_tools, reset_clients
    from myagentflow.tools.registry import ToolRegistry

    config = McpConfig(servers=[{"name": "fs", "command": ["fake"]}])
    registry = ToolRegistry()
    names = register_configured_mcp_tools(
        registry, config=config, client_factory=FakeMcpClient
    )

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


def test_mcp_tool_allow_via_config_or_env(monkeypatch):
    from myagentflow.agents.middlewares.policy import PolicyMiddleware
    from myagentflow.config.app_config import (
        AppConfig,
        reset_app_config,
        set_app_config,
    )
    from myagentflow.config.mcp_config import McpConfig
    from myagentflow.sandbox.approvals import ApprovalStore
    from myagentflow.tools.executor import ToolCallRequest

    request = ToolCallRequest(tool_call={"name": "mcp__fs__read_file", "args": {}, "id": "c1"})

    # 环境变量 MYAF_MCP_ALLOW：运行时覆盖仍然有效
    monkeypatch.setenv("MYAF_MCP_ALLOW", "mcp__fs__read_file")
    assert PolicyMiddleware(ApprovalStore()).wrap_tool_call(request, lambda r: "ok") == "ok"

    # config.yaml 的 mcp.allow：结构化配置同样放行（此时不带环境变量）
    monkeypatch.delenv("MYAF_MCP_ALLOW", raising=False)
    set_app_config(AppConfig(mcp=McpConfig(allow=["mcp__fs__read_file"])))
    try:
        assert PolicyMiddleware(ApprovalStore()).wrap_tool_call(request, lambda r: "ok") == "ok"
    finally:
        reset_app_config()  # 还原「未加载」状态，避免污染其它测试


def test_parse_specs_defaults_to_app_config(monkeypatch, tmp_path):
    """不设环境变量、只写 config.yaml 的 mcp 段也能装配（缺省走 get_app_config）。"""
    from myagentflow.config.app_config import reset_app_config
    from myagentflow.mcp.assembly import parse_server_specs

    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        "mcp:\n"
        "  servers:\n"
        "    - name: fs\n"
        "      command: [echo]\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("MYAGENTFLOW_CONFIG_PATH", str(config_file))
    monkeypatch.delenv("MYAF_MCP_SERVERS", raising=False)
    reset_app_config()
    try:
        specs = parse_server_specs()
        assert [s["name"] for s in specs] == ["fs"]
        assert specs[0]["prefix"] == "mcp__fs__"
    finally:
        reset_app_config()
