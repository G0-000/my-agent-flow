"""第一个内置工具：echo。它的价值是「证明通路」，不是功能。"""
from __future__ import annotations

from myagentflow.tools.registry import ToolRegistry, ToolSpec


def _echo(text: str) -> str:
    return text


def register_echo(registry: ToolRegistry) -> None:
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
