"""最小 Agent：一个节点 + 两条边。

刻意不做工具循环：先把「单轮」跑通，后面每章只在这张图上加节点/加边。
"""
from __future__ import annotations

from typing import Any

from langgraph.graph import END, START, MessagesState, StateGraph


def build_graph(model: Any, checkpointer: Any = None):
    graph = StateGraph(MessagesState)

    def call_model(state: MessagesState):
        # 唯一职责：把当前历史交给模型，把回复塞回 messages
        reply = model.invoke(state["messages"])
        return {"messages": [reply]}

    graph.add_node("call_model", call_model)
    graph.add_edge(START, "call_model")
    graph.add_edge("call_model", END)

    # checkpointer 允许 None：本章先不落盘，02/01 再注入
    return graph.compile(checkpointer=checkpointer)
