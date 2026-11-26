"""一、文件说明
    最小 Agent 图：模型节点 + 可选工具循环。
    默认仍是「单轮」：不传 tools 时 START → call_model → END；
    传 tools 时多一个 tools 节点，模型发起 tool_calls 就执行并回灌，直到不再调用或达到上限。

二、目录结构
    packages/harness/myagentflow/agents/lead_agent/
    ├── __init__.py
    └── graph.py  ← 本文件

三、关键方法
    build_graph()  建图：单轮或「模型 ↔ 工具」循环；可选挂 checkpointer 保留同线程历史。
    route_after_model()  只做一件事：有 tool_calls 且未超轮次就去 tools，否则结束。
"""
from __future__ import annotations

from typing import Any

from langchain_core.messages import SystemMessage, ToolMessage
from langgraph.graph import END, START, MessagesState, StateGraph

DEFAULT_MAX_TOOL_ROUNDS = 4


def build_graph(
    model: Any,
    checkpointer: Any = None,
    *,
    tools: Any = None,
    max_tool_rounds: int = DEFAULT_MAX_TOOL_ROUNDS,
    system_prompt: str | None = None,
):
    """建 Agent 图。

    Args:
        model: 聊天模型；传 tools 时必须支持 ``bind_tools``。
        checkpointer: 可选检查点；不传则不保留线程历史。
        tools: 可选 ``ToolRegistry``；不传就是单轮图。
        max_tool_rounds: 最多执行多少次工具批次，防止模型无限调用。
        system_prompt: 每轮临时加到消息前面，不写入检查点历史。
    """
    graph = StateGraph(MessagesState)

    def call_model(state: MessagesState):
        """把当前历史（含临时 system）交给模型，把回复塞回 messages。"""
        messages = list(state["messages"])
        if system_prompt:
            messages = [SystemMessage(content=system_prompt), *messages]
        bound = model.bind_tools(tools.schemas()) if tools is not None else model
        reply = bound.invoke(messages)
        return {"messages": [reply]}

    def call_tools(state: MessagesState):
        """执行最后一条 AI 消息里的全部 tool_calls，逐条回灌 ToolMessage。"""
        last = state["messages"][-1]
        results: list[ToolMessage] = []
        for call in getattr(last, "tool_calls", None) or []:
            name = str(call.get("name") or "")
            args = call.get("args") or {}
            call_id = str(call.get("id") or "")
            try:
                output = tools.call(name, args)
                content = str(output)
            except Exception as exc:  # 工具失败要回灌给模型，不能把整轮打断
                content = f"ERROR: {type(exc).__name__}: {exc}"
            results.append(ToolMessage(content=content, tool_call_id=call_id))
        return {"messages": results}

    def route_after_model(state: MessagesState) -> str:
        """有 tool_calls 且未超轮次就去 tools，否则结束。"""
        last = state["messages"][-1]
        if not getattr(last, "tool_calls", None):
            return END
        used = sum(isinstance(m, ToolMessage) for m in state["messages"])
        return "tools" if used < max_tool_rounds else END

    graph.add_node("call_model", call_model)
    graph.add_edge(START, "call_model")

    if tools is not None:
        graph.add_node("tools", call_tools)
        graph.add_conditional_edges(
            "call_model",
            route_after_model,
            {"tools": "tools", END: END},
        )
        graph.add_edge("tools", "call_model")
    else:
        graph.add_edge("call_model", END)

    # checkpointer 允许 None：不传就是无状态单轮，传了才累积同线程历史
    return graph.compile(checkpointer=checkpointer)
