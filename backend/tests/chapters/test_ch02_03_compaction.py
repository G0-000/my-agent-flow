"""第 02.3 章：压缩、续写与再注入的行为测试。"""

from __future__ import annotations

from langchain_core.messages import AIMessage, HumanMessage


def test_needs_continuation_only_for_length_finish():
    from myagentflow.context.short_term import needs_continuation

    assert needs_continuation(AIMessage(content="半句", response_metadata={"finish_reason": "length"}))
    assert needs_continuation(AIMessage(content="半句", response_metadata={"stop_reason": "max_tokens"}))
    assert not needs_continuation(AIMessage(content="完整", response_metadata={"finish_reason": "stop"}))
    assert not needs_continuation(
        AIMessage(
            content="",
            tool_calls=[{"name": "echo", "args": {}, "id": "c"}],
            response_metadata={"finish_reason": "length"},
        )
    )


class TruncatedModel:
    """第一次返回 length，第二次返回收尾；记录每次看到的消息。"""

    def __init__(self) -> None:
        self.seen: list[list] = []

    def bind_tools(self, schemas):
        del schemas
        return self

    def invoke(self, messages, *_args, **_kwargs):
        self.seen.append(list(messages))
        if len(self.seen) == 1:
            return AIMessage(
                content="前半段。",
                response_metadata={"finish_reason": "length"},
            )
        return AIMessage(content="后半段。", response_metadata={"finish_reason": "stop"})


def test_graph_auto_continues_truncated_answer():
    from myagentflow.agents.lead_agent.graph import build_graph

    model = TruncatedModel()
    graph = build_graph(model, max_continuations=2)
    out = graph.invoke({"messages": [HumanMessage(content="写长文")]})

    assert out["messages"][-1].content == "前半段。后半段。"
    assert len(model.seen) == 2
    assert model.seen[1][-1].content.startswith("上一条回答因长度限制被截断")


def test_graph_does_not_continue_normal_answer():
    from myagentflow.agents.lead_agent.graph import build_graph

    class NormalModel(TruncatedModel):
        def invoke(self, messages, *_args, **_kwargs):
            self.seen.append(list(messages))
            return AIMessage(content="完整回答", response_metadata={"finish_reason": "stop"})

    model = NormalModel()
    out = build_graph(model, max_continuations=2).invoke(
        {"messages": [HumanMessage(content="普通问题")]}
    )

    assert out["messages"][-1].content == "完整回答"
    assert len(model.seen) == 1


class RecordingModel:
    def __init__(self) -> None:
        self.seen: list[list] = []

    def bind_tools(self, schemas):
        del schemas
        return self

    def invoke(self, messages, *_args, **_kwargs):
        self.seen.append(list(messages))
        return AIMessage(content="ok")


def test_graph_applies_context_manager_before_model():
    from myagentflow.agents.lead_agent.graph import build_graph
    from myagentflow.context.short_term import ContextManager

    model = RecordingModel()
    manager = ContextManager(context_length=1000)
    history = [
        HumanMessage(content="旧问题" + "甲" * 300),
        AIMessage(content="旧回答" + "乙" * 300),
        HumanMessage(content="新问题" + "丙" * 300),
    ]
    graph = build_graph(model, context_manager=manager)
    graph.invoke({"messages": history})

    seen = model.seen[0]
    assert all("旧问题" not in str(m.content) for m in seen)
    assert "新问题" in str(seen[-1].content)
