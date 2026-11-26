"""第 01.5 章：工具调用循环的最小行为测试。

覆盖：
- 模型发起 tool_calls → 图执行工具 → ToolMessage 回灌 → 模型给出最终回答
- 工具失败时错误回灌给模型，不把整轮打断
- 达到 max_tool_rounds 后停止，不无限循环
"""

from __future__ import annotations

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage


class ScriptedToolModel:
    """脚本模型：第一次要求调 echo，看到 ToolMessage 后给最终回答。"""

    def __init__(self) -> None:
        self.schemas = None
        self.calls = 0

    def bind_tools(self, schemas):
        self.schemas = schemas
        return self

    def invoke(self, messages, *_args, **_kwargs):
        self.calls += 1
        if any(isinstance(m, ToolMessage) for m in messages):
            return AIMessage(content=f"final: {messages[-1].content}")
        return AIMessage(
            content="",
            tool_calls=[{"name": "echo", "args": {"text": "hi"}, "id": "call-1"}],
        )


def test_tool_loop_executes_and_feeds_back():
    from myagentflow.agents.lead_agent.graph import build_graph
    from myagentflow.tools.builtins.echo import register_echo
    from myagentflow.tools.registry import ToolRegistry

    registry = ToolRegistry()
    register_echo(registry)
    model = ScriptedToolModel()
    graph = build_graph(model, tools=registry)

    out = graph.invoke({"messages": [HumanMessage(content="用工具")]})

    assert model.schemas and model.schemas[0]["function"]["name"] == "echo"
    assert any(isinstance(m, ToolMessage) and m.content == "hi" for m in out["messages"])
    assert out["messages"][-1].content == "final: hi"


def test_tool_error_is_fed_back():
    from myagentflow.agents.lead_agent.graph import build_graph
    from myagentflow.tools.registry import ToolRegistry

    class MissingToolModel(ScriptedToolModel):
        def invoke(self, messages, *_args, **_kwargs):
            if any(isinstance(m, ToolMessage) for m in messages):
                return AIMessage(content="final")
            return AIMessage(
                content="",
                tool_calls=[{"name": "missing", "args": {}, "id": "call-x"}],
            )

    graph = build_graph(MissingToolModel(), tools=ToolRegistry())
    out = graph.invoke({"messages": [HumanMessage(content="调不存在的工具")]})

    tool_msg = next(m for m in out["messages"] if isinstance(m, ToolMessage))
    assert tool_msg.content.startswith("ERROR: KeyError")
    assert out["messages"][-1].content == "final"


def test_max_tool_rounds_stops():
    from myagentflow.agents.lead_agent.graph import build_graph
    from myagentflow.tools.builtins.echo import register_echo
    from myagentflow.tools.registry import ToolRegistry

    class AlwaysToolModel(ScriptedToolModel):
        def invoke(self, messages, *_args, **_kwargs):
            return AIMessage(
                content="",
                tool_calls=[{"name": "echo", "args": {"text": "x"}, "id": "call"}],
            )

    registry = ToolRegistry()
    register_echo(registry)
    graph = build_graph(AlwaysToolModel(), tools=registry, max_tool_rounds=2)
    out = graph.invoke({"messages": [HumanMessage(content="循环")]})

    assert sum(isinstance(m, ToolMessage) for m in out["messages"]) == 2
