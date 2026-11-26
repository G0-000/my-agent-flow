"""第 03.6 章：MCP 客户端与 Skills 注册的最小行为测试。

覆盖：
- MCP：stdio 子进程按 JSON-RPC 应答 initialize / tools/list / tools/call
- MCP 错误：服务返回 error 时抛 RuntimeError，不把 error 当结果
- Skills：manifest 校验、重复安装拒绝、版本号格式
- 插件加载：entry 可导入时返回函数；导入失败返回 None 且不抛
"""

from __future__ import annotations

import json
import sys
import textwrap

import pytest

_SERVER = textwrap.dedent(
    """
    import json, sys

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        req = json.loads(line)
        method = req.get("method")
        if method == "initialize":
            result = {"protocolVersion": "2024-11-05", "serverInfo": {"name": "fake"}}
        elif method == "tools/list":
            result = {"tools": [{"name": "echo", "description": "echo text"}]}
        elif method == "tools/call":
            args = (req.get("params") or {}).get("arguments") or {}
            result = {"content": [{"type": "text", "text": str(args.get("text", ""))}]}
        elif method == "boom":
            print(json.dumps({"jsonrpc": "2.0", "id": req.get("id"),
                              "error": {"code": -32000, "message": "boom"}}), flush=True)
            continue
        else:
            result = {}
        print(json.dumps({"jsonrpc": "2.0", "id": req.get("id"), "result": result}), flush=True)
    """
)


def test_mcp_stdio_roundtrip(tmp_path):
    from myagentflow.mcp.client import McpClient

    script = tmp_path / "fake_mcp.py"
    script.write_text(_SERVER, encoding="utf-8")

    client = McpClient([sys.executable, str(script)])
    try:
        init = client.initialize()
        assert init["serverInfo"]["name"] == "fake"

        tools = client.list_tools()
        assert tools[0]["name"] == "echo"

        out = client.call_tool("echo", {"text": "hi"})
        assert out["content"][0]["text"] == "hi"

        with pytest.raises(RuntimeError, match="MCP 错误"):
            client._request("boom")
    finally:
        client.close()


def _pkg(tmp_path, name="demo", version="1.0.0", entry="json:dumps"):
    pkg = tmp_path / f"{name}-{version}"
    pkg.mkdir(exist_ok=True)
    (pkg / "manifest.json").write_text(
        json.dumps({"name": name, "version": version, "entry": entry}), encoding="utf-8"
    )
    return pkg


def test_skill_manifest_and_install(tmp_path):
    from myagentflow.skills.registry import SkillRegistry

    reg = SkillRegistry()
    m = reg.install(_pkg(tmp_path))
    assert m.name == "demo"
    assert reg.list() == [{"name": "demo", "version": "1.0.0"}]

    with pytest.raises(ValueError, match="已安装"):
        reg.install(_pkg(tmp_path, name="demo"))


def test_skill_manifest_rejects_bad_version(tmp_path):
    from myagentflow.skills.registry import read_manifest

    with pytest.raises(ValueError, match="版本号不合法"):
        read_manifest(_pkg(tmp_path, version="v1.0"))


def test_plugin_load_and_failure_isolation():
    from myagentflow.skills.loader import PluginSpec, load

    assert load(PluginSpec(name="ok", entry="json:dumps")) is not None
    assert load(PluginSpec(name="bad", entry="no_such_module:fn")) is None
