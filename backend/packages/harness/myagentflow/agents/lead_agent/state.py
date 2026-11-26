"""Agent 图状态：消息 + 本轮产物。

为什么单独定义状态：MessagesState 只装 messages，产物（文件/链接）没有地方放；
把产物塞进 ToolMessage 文本里，前端只能靠正则猜，且模型会把它当成事实。
"""
from __future__ import annotations

from typing import Annotated, Any, TypedDict

from langgraph.graph.message import add_messages


def merge_artifacts(
    left: dict[str, dict[str, Any]] | None,
    right: dict[str, dict[str, Any]] | None,
) -> dict[str, dict[str, Any]]:
    """按稳定键合并：同一路径/URL 覆盖旧值，不重复堆积。"""
    merged = dict(left or {})
    merged.update(right or {})
    return merged


class AgentState(TypedDict):
    messages: Annotated[list[Any], add_messages]
    artifacts: Annotated[dict[str, dict[str, Any]], merge_artifacts]
