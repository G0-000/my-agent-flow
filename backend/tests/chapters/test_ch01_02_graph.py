from __future__ import annotations

from langchain_core.messages import AIMessage, HumanMessage


class EchoModel:
    """假模型：不联网，只回显。测试里所有「模型」都该长这样。"""

    def invoke(self, messages, *_args, **_kwargs):
        return AIMessage(content="echo: " + messages[-1].content)


def test_single_turn():
    from myagentflow.agents.lead_agent.graph import build_graph

    graph = build_graph(EchoModel())
    out = graph.invoke({"messages": [HumanMessage(content="你好")]})
    assert out["messages"][-1].content == "echo: 你好"


def test_same_thread_keeps_history():
    from langchain_core.messages import HumanMessage
    from langgraph.checkpoint.memory import InMemorySaver
    from myagentflow.agents.lead_agent.graph import build_graph

    graph = build_graph(EchoModel(), InMemorySaver())
    cfg = {"configurable": {"thread_id": "t1"}}

    graph.invoke({"messages": [HumanMessage(content="一")]}, cfg)
    out = graph.invoke({"messages": [HumanMessage(content="二")]}, cfg)

    # 4 条 = 用户一、回复一、用户二、回复二；说明检查点真的在累积
    assert len(out["messages"]) == 4
