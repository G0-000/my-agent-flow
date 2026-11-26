"""MCP → ToolRegistry 的桥：外部 MCP server 的工具变成本地工具。

对齐 EvoFlow 的「MCP 工具进注册表」这一步，只做最小面：
`tools/list` → `ToolSpec`（name/description/inputSchema）→ `tools/call` 回灌文本。
未做：HTTP/SSE 传输、OAuth、重连、工具名冲突策略、生命周期托管。
"""
from __future__ import annotations

import json
from typing import Any, Protocol

from myagentflow.tools.registry import ToolRegistry, ToolSpec


class McpToolClient(Protocol):
    def list_tools(self) -> list[dict[str, Any]]: ...
    def call_tool(self, name: str, args: dict[str, Any]) -> Any: ...


def _result_to_text(result: Any) -> str:
    """MCP 返回 content blocks；只拼文本，其它类型保留 JSON 便于排查。"""
    if isinstance(result, dict):
        blocks = result.get("content")
        if isinstance(blocks, list):
            parts = [
                str(b.get("text") or "")
                for b in blocks
                if isinstance(b, dict) and b.get("type") == "text"
            ]
            if any(parts):
                return "".join(parts)
    if isinstance(result, str):
        return result
    return json.dumps(result, ensure_ascii=False, default=str)


def register_mcp_tools(
    registry: ToolRegistry,
    client: McpToolClient,
    *,
    prefix: str = "mcp__",
) -> list[str]:
    """把 MCP 工具注册进本地注册表，返回注册后的名字。

    加前缀是为了避免与内置工具重名；重名会由 `ToolRegistry.register` 直接拒绝，
    这里不静默覆盖。
    """
    registered: list[str] = []
    for tool in client.list_tools():
        raw_name = str(tool.get("name") or "").strip()
        if not raw_name:
            continue
        local_name = f"{prefix}{raw_name}" if prefix else raw_name
        schema = tool.get("inputSchema") or tool.get("input_schema") or {"type": "object", "properties": {}}
        registry.register(
            ToolSpec(
                name=local_name,
                description=str(tool.get("description") or f"MCP 工具 {raw_name}"),
                input_schema=schema,
                fn=_make_caller(client, raw_name),
            )
        )
        registered.append(local_name)
    return registered


def _make_caller(client: McpToolClient, remote_name: str):
    """闭包绑定远端名，避免循环变量晚绑定导致所有工具都调到最后一个。"""

    def call(**kwargs: Any) -> str:
        return _result_to_text(client.call_tool(remote_name, kwargs))

    return call
