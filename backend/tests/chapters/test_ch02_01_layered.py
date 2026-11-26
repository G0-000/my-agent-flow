"""02.1 / 02.3：分层预算与旧工具结果裁剪。

覆盖：
- 四层配额不超过压缩阈值，历史仍有预算
- 旧轮工具结果只留头尾，最近一轮保持完整
- ContextManager 的滑窗预算会被 tool_tokens 与历史配额共同压住
"""

from __future__ import annotations

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage


def test_layered_quotas_fit_threshold():
    from myagentflow.context.budget import compact_threshold, layered_quotas

    threshold = compact_threshold(256_000)
    quotas = layered_quotas(
        256_000,
        system_tokens=2_000,
        tool_tokens=3_000,
        tool_result_tokens=10_000,
    )
    assert quotas["history"] > 0
    assert quotas["system"] == 2_000
    assert quotas["tools"] == 3_000
    assert quotas["tool_results"] == 10_000
    assert sum(quotas.values()) <= threshold


def test_prune_old_tool_results_keeps_recent_group():
    from myagentflow.context.short_term import prune_tool_results

    big = "A" * 2_000
    messages = [
        HumanMessage(content="第一轮"),
        AIMessage(content="", tool_calls=[{"name": "echo", "args": {}, "id": "c1"}]),
        ToolMessage(content=big, tool_call_id="c1"),
        HumanMessage(content="第二轮"),
        AIMessage(content="", tool_calls=[{"name": "echo", "args": {}, "id": "c2"}]),
        ToolMessage(content=big, tool_call_id="c2"),
    ]

    pruned = prune_tool_results(messages, keep_recent_groups=1, head_chars=100, tail_chars=100)

    old_tool = next(m for m in pruned if isinstance(m, ToolMessage) and m.tool_call_id == "c1")
    new_tool = next(m for m in pruned if isinstance(m, ToolMessage) and m.tool_call_id == "c2")
    assert len(old_tool.content) < len(big)
    assert "旧工具结果已裁剪" in old_tool.content
    assert new_tool.content == big


def test_prepare_uses_tool_tokens_and_history_quota():
    from myagentflow.context.short_term import ContextManager

    manager = ContextManager(context_length=10_000, full_ratio=0.5)
    messages = []
    for i in range(10):
        messages.append(HumanMessage(content=f"问题{i} " + "字" * 300))
        messages.append(AIMessage(content="回答 " + "字" * 300))

    prepared = manager.prepare(messages, reserved_tokens=200, tool_tokens=5_000)

    assert prepared.strategy != "full"
    assert prepared.tokens_after < prepared.tokens_before
    # 最后一轮必须保留，不能把当前用户消息裁掉
    assert any(isinstance(m, HumanMessage) and "问题9" in m.content for m in prepared.messages)
