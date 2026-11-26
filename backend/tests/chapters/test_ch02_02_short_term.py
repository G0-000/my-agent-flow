"""第 02.2 章：短期记忆三策略的行为测试。"""

from __future__ import annotations

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage


def _turn(i: int, size: int = 300):
    return [
        HumanMessage(content=f"用户{i}" + "甲" * size),
        AIMessage(content=f"回答{i}" + "乙" * size),
    ]


def test_full_strategy_keeps_all_turns():
    from myagentflow.context.short_term import ContextManager

    messages = [*_turn(1, 20), *_turn(2, 20)]
    prepared = ContextManager(context_length=1000).prepare(messages)

    assert prepared.strategy == "full"
    assert prepared.messages == messages


def test_sliding_window_drops_old_turns_but_keeps_last_human():
    from myagentflow.context.short_term import ContextManager

    messages = [*_turn(1), *_turn(2), *_turn(3)]
    prepared = ContextManager(context_length=1000).prepare(messages)

    assert prepared.strategy == "sliding_window"
    assert prepared.messages[-2].content.startswith("用户3")
    assert all("用户1" not in str(m.content) for m in prepared.messages)
    assert prepared.tokens_after < prepared.tokens_before


def test_summary_strategy_replaces_old_turns_with_system_message():
    from myagentflow.context.short_term import SUMMARY_MARKER, ContextManager

    messages = [*_turn(1), *_turn(2), *_turn(3), *_turn(4)]
    prepared = ContextManager(
        context_length=1000,
        summarizer=lambda old: "用户目标：复刻上下文；未完成：压缩测试。",
    ).prepare(messages)

    assert prepared.strategy == "summary"
    assert prepared.summarized is True
    assert prepared.messages[0].type == "system"
    assert SUMMARY_MARKER in prepared.messages[0].content
    assert prepared.messages[-2].content.startswith("用户4")
    assert all("用户1" not in str(m.content) for m in prepared.messages)


def test_summary_failure_falls_back_to_sliding_window():
    from myagentflow.context.short_term import ContextManager

    def boom(_old):
        raise RuntimeError("summarizer down")

    messages = [*_turn(1), *_turn(2), *_turn(3), *_turn(4)]
    prepared = ContextManager(context_length=1000, summarizer=boom).prepare(messages)

    assert prepared.strategy == "sliding_window"
    assert prepared.summarized is False
    assert prepared.messages[-2].content.startswith("用户4")


def test_groups_do_not_split_tool_call_from_tool_message():
    from myagentflow.context.short_term import split_message_groups

    messages = [
        HumanMessage(content="查一下"),
        AIMessage(content="", tool_calls=[{"name": "echo", "args": {}, "id": "c1"}]),
        ToolMessage(content="结果", tool_call_id="c1"),
        AIMessage(content="完成"),
    ]
    groups = split_message_groups(messages)

    assert len(groups) == 1
    assert [m.type for m in groups[0]] == ["human", "ai", "tool", "ai"]
