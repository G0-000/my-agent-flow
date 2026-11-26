"""按配置装配 MCP 工具：聊天入口不再只认内置工具。

配置来源是 ``MYAF_MCP_SERVERS``（JSON 数组），例如：
``[{"name":"fs","command":["npx","-y","@modelcontextprotocol/server-filesystem","."]}]``

为什么用环境变量而不是 config.yaml：MCP server 是可选的本地进程，
默认不配置就不启动；把它写进主配置会让「离线跑通」多一个必填项。
"""
from __future__ import annotations

import json
import logging
import os
from collections.abc import Callable
from typing import Any

from myagentflow.mcp.bridge import McpToolClient, register_mcp_tools
from myagentflow.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)

ENV = "MYAF_MCP_SERVERS"

# 进程内保留客户端：注册进 registry 的闭包要一直能调到子进程。
_clients: list[McpToolClient] = []


def parse_server_specs(raw: str | None = None) -> list[dict[str, Any]]:
    """解析配置；坏 JSON / 缺 command 的条目直接跳过，不让启动失败。"""
    text = (raw if raw is not None else os.getenv(ENV, "")).strip()
    if not text:
        return []
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        logger.warning("invalid %s: not JSON", ENV)
        return []
    if not isinstance(data, list):
        logger.warning("invalid %s: expected a list", ENV)
        return []
    specs: list[dict[str, Any]] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        command = item.get("command")
        if not isinstance(command, list) or not command:
            logger.warning("skip MCP server without command: %r", item.get("name"))
            continue
        specs.append(
            {
                "name": str(item.get("name") or "mcp"),
                "command": [str(x) for x in command],
                "prefix": str(item.get("prefix") or f"mcp__{item.get('name') or 'server'}__"),
            }
        )
    return specs


def register_configured_mcp_tools(
    registry: ToolRegistry,
    *,
    client_factory: Callable[[list[str]], McpToolClient] | None = None,
) -> list[str]:
    """把配置里的 MCP server 全部接进注册表；单个 server 失败不影响其它。"""
    specs = parse_server_specs()
    if not specs:
        return []
    if client_factory is None:
        from myagentflow.mcp.client import McpClient

        def client_factory(command: list[str]) -> McpToolClient:
            return McpClient(command)

    registered: list[str] = []
    for spec in specs:
        try:
            client = client_factory(spec["command"])
            init = getattr(client, "initialize", None)
            if callable(init):
                init()
            names = register_mcp_tools(registry, client, prefix=spec["prefix"])
            _clients.append(client)
            registered.extend(names)
            logger.info("mcp server %s registered %d tools", spec["name"], len(names))
        except Exception:
            logger.exception("mcp server %s failed to register", spec["name"])
    return registered


def reset_clients() -> None:
    """测试/退出用：关掉子进程并清空引用。"""
    global _clients
    for client in _clients:
        close = getattr(client, "close", None)
        if callable(close):
            try:
                close()
            except Exception:
                logger.exception("mcp client close failed")
    _clients = []
