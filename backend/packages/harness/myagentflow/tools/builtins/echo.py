"""一、文件说明
    第一个内置工具：echo。它的价值是「证明通路」，不是功能。

二、目录结构
    packages/harness/myagentflow/tools/builtins/
    ├── __init__.py
    └── echo.py  ← 本文件

三、关键方法
    _echo()          原样返回输入，用于验证工具通路。
    register_echo()  把 echo 工具连同 schema 注册进注册表。
"""
from __future__ import annotations

from myagentflow.tools.registry import ToolRegistry, ToolSpec


def _echo(text: str) -> str:
    """原样返回输入，用于验证工具通路。"""
    return text


def register_echo(registry: ToolRegistry) -> None:
    """把 echo 工具连同 schema 注册进注册表。"""
    registry.register(
        ToolSpec(
            name="echo",
            description="把输入原样返回，用于验证工具通路",
            input_schema={
                "type": "object",
                "properties": {"text": {"type": "string", "description": "要回显的文本"}},
                "required": ["text"],
            },
            fn=_echo,
        )
    )
