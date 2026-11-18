"""一、文件说明
    工具注册表：一个数据结构 + 三个方法。
    为什么要 ToolSpec 而不是裸函数：模型要的是 name/description/JSON Schema，
    执行要的是可调用对象，两者必须绑在一起，否则迟早对不上。

二、目录结构
    packages/harness/myagentflow/tools/
    ├── __init__.py
    └── registry.py  ← 本文件

三、关键方法
    ToolSpec      一个工具的完整声明：名字、描述、JSON Schema、可调用对象。
    ToolRegistry  工具注册表：注册、查找、调用；重名直接拒绝。
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ToolSpec:
    """一个工具的完整声明：名字、描述、JSON Schema、可调用对象。"""
    name: str
    description: str
    input_schema: dict[str, Any]
    fn: Callable[..., Any]


class ToolRegistry:
    """工具注册表：注册、查找、调用；重名直接拒绝。"""
    def __init__(self) -> None:
        self._tools: dict[str, ToolSpec] = {}

    def register(self, spec: ToolSpec) -> None:
        if spec.name in self._tools:
            raise ValueError(f"工具重名：{spec.name}")
        self._tools[spec.name] = spec

    def schemas(self) -> list[dict[str, Any]]:
        """给模型看的形状。字段名照 OpenAI function calling，别自创。"""
        return [
            {
                "type": "function",
                "function": {
                    "name": s.name,
                    "description": s.description,
                    "parameters": s.input_schema,
                },
            }
            for s in self._tools.values()
        ]

    def call(self, name: str, args: dict[str, Any]) -> Any:
        spec = self._tools.get(name)
        if spec is None:
            raise KeyError(f"未注册的工具：{name}")
        return spec.fn(**args)
