"""一、文件说明
    MCP 配置节：外部工具服务器的声明式配置，和 models/checkpointer/storage 同级。
    为什么进 config.yaml：MCP server 是运行时依赖，不是一次性开关；
    写进结构化配置后才能被配置检查、复用与审计。环境变量只做运行时覆盖。

二、目录结构
    packages/harness/myagentflow/config/
    ├── app_config.py       ← 根配置，挂 mcp 段
    └── mcp_config.py       ← 本文件：server 列表 + 免审批工具白名单

三、关键方法
    McpServerConfig  一个 server：name / command / prefix（可选）
    McpConfig        servers 列表 + allow 白名单
"""
from __future__ import annotations

from pydantic import BaseModel, Field


class McpServerConfig(BaseModel):
    """一个 MCP server：用 command 启动 stdio 子进程。"""

    name: str
    command: list[str]
    prefix: str | None = Field(default=None, description="工具名前缀；缺省用 mcp__<name>__")


class McpConfig(BaseModel):
    """MCP 段：默认空，离线跑通不需要启动任何子进程。"""

    servers: list[McpServerConfig] = Field(default_factory=list)
    allow: list[str] = Field(
        default_factory=list,
        description="免审批的 MCP 工具全名；不在名单里的默认需要审批",
    )
