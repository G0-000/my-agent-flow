"""一、文件说明
    只读检查点读线程状态：不编译图。
    为什么独立成文件：刷新页面、拉历史这类高频路径会反复调它。
    一旦有人顺手在这里 compile/invoke 图，整条读路径就变成秒级。

二、目录结构
    packages/harness/myagentflow/agents/checkpointer/
    ├── __init__.py  检查点层：对外只暴露「拿 saver / 重置 / 一次性上下文」三件事。
    ├── provider.py  检查点提供者：单例 + 一次性上下文（memory / sqlite / pos
    └── thread_state_reader.py  ← 本文件

三、关键方法
    read_thread_state()  返回最新检查点的最小快照；线程不存在返回 None。
"""
from __future__ import annotations

from typing import Any

from langgraph.types import Checkpointer


def read_thread_state(checkpointer: Checkpointer, thread_id: str) -> dict[str, Any] | None:
    """返回最新检查点的最小快照；线程不存在返回 None。

    返回结构刻意收窄：只给 checkpoint_id / values / metadata。
    要完整对话去消息表找 —— 检查点里没有消息，这是设计，不是缺陷。
    """
    config = {"configurable": {"thread_id": str(thread_id)}}
    tup = checkpointer.get_tuple(config)
    if tup is None:
        return None

    checkpoint = tup.checkpoint or {}
    return {
        "checkpoint_id": checkpoint.get("id"),
        "values": checkpoint.get("channel_values", {}),
        "metadata": dict(tup.metadata or {}),
    }
