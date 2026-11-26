"""按配置装配 MCP 工具：聊天入口不再只认内置工具。

配置来源是 config.yaml 的 ``mcp.servers`` 段（与 models/checkpointer/storage 同级），例如::

    mcp:
      servers:
        - name: fs
          command: [npx, -y, "@modelcontextprotocol/server-filesystem", "."]

为什么进 config.yaml：MCP server 是运行时依赖，声明式配置才能被检查、复用与审计；
环境变量只保留 ``MYAF_MCP_ALLOW``，作为免审批白名单的运行时追加。
"""
from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from myagentflow.config.app_config import get_app_config
from myagentflow.config.mcp_config import McpConfig
from myagentflow.mcp.bridge import McpToolClient, register_mcp_tools
from myagentflow.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)

# 进程内保留客户端：注册进 registry 的闭包要一直能调到子进程。
_clients: list[McpToolClient] = []


def parse_server_specs(config: McpConfig | None = None) -> list[dict[str, Any]]:
    """把 mcp.servers 摊平成装配项；缺 command 的条目跳过，不让启动失败。"""
    if config is None:
        config = get_app_config().mcp
    specs: list[dict[str, Any]] = []
    for item in config.servers:
        if not item.command:
            logger.warning("skip MCP server without command: %r", item.name)
            continue
        specs.append(
            {
                "name": item.name,
                "command": list(item.command),
                "prefix": item.prefix or f"mcp__{item.name}__",
            }
        )
    return specs


def register_configured_mcp_tools(
    registry: ToolRegistry,
    *,
    config: McpConfig | None = None,
    client_factory: Callable[[list[str]], McpToolClient] | None = None,
) -> list[str]:
    """把配置里的 MCP server 全部接进注册表；单个 server 失败不影响其它。"""
    specs = parse_server_specs(config)
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
