#!/usr/bin/env python3
# 第 02 篇最小闭环：长对话在预算内继续，关键事实不丢。
# 构造超预算长对话（关键事实放在最早的轮次）→ ContextManager 摘要裁剪
# → 校验 strategy=summary、token 下降、关键事实保留、最后一轮不丢
# → 再过一遍图，确认模型实际看到的输入带摘要。结果写 tmp/ch02/summary.txt。

from __future__ import annotations

import sys
from pathlib import Path

from langchain_core.messages import AIMessage, HumanMessage

from myagentflow.agents.lead_agent.graph import build_graph
from myagentflow.context.short_term import SUMMARY_MARKER, ContextManager

KEY_FACT = "交付日期是 11 月 30 日"
NEW_QUESTION = "交付日期是什么时候？"


def _extractive_summarizer(old_messages):
    """离线摘要替身：只保留含「记住：」的句子，模拟关键事实抽取。"""
    facts: list[str] = []
    for message in old_messages:
        for line in str(message.content).split("。"):
            line = line.strip()
            if "记住：" in line and line not in facts:
                facts.append(line)
    return "关键事实：" + "；".join(facts) if facts else "（旧对话中无关键事实）"


class RecordingModel:
    """记录每次调用看到的消息，返回固定回答。"""

    def __init__(self) -> None:
        self.seen: list[list] = []

    def bind_tools(self, schemas):
        del schemas
        return self

    def invoke(self, messages, *_args, **_kwargs):
        self.seen.append(list(messages))
        return AIMessage(content="已根据摘要与最新提问作答。")


def _build_history() -> list:
    history: list = [
        HumanMessage(content=f"请记住：{KEY_FACT}。"),
        AIMessage(content="好的，已记住这个交付日期。"),
    ]
    for i in range(1, 7):  # 六轮闲聊把历史顶过预算
        history.append(HumanMessage(content=f"闲聊{i}：" + "甲" * 150))
        history.append(AIMessage(content=f"回复{i}：" + "乙" * 150))
    history.append(HumanMessage(content=NEW_QUESTION))
    return history


def main() -> int:
    history = _build_history()
    manager = ContextManager(context_length=500, summarizer=_extractive_summarizer)
    prepared = manager.prepare(history)

    summary_message = prepared.messages[0]
    checks = {
        "strategy_is_summary": prepared.strategy == "summary",
        "summarized": prepared.summarized is True,
        "tokens_shrunk": prepared.tokens_after < prepared.tokens_before,
        "marker_in_summary": SUMMARY_MARKER in str(summary_message.content),
        "key_fact_kept": KEY_FACT in str(summary_message.content),
        "last_turn_kept": str(prepared.messages[-1].content) == NEW_QUESTION,
    }
    failed = [name for name, ok in checks.items() if not ok]
    if failed:
        print(f"FAILED: {failed}", file=sys.stderr)
        return 1

    model = RecordingModel()
    graph = build_graph(model, context_manager=manager)
    graph.invoke({"messages": history})
    graph_saw_summary = (
        bool(model.seen)
        and model.seen[0][0].type == "system"
        and KEY_FACT in str(model.seen[0][0].content)
        and str(model.seen[0][-1].content) == NEW_QUESTION
    )
    if not graph_saw_summary:
        print("FAILED: graph did not see the summary", file=sys.stderr)
        return 1

    out_dir = Path(__file__).resolve().parents[1] / "tmp" / "ch02"
    out_dir.mkdir(parents=True, exist_ok=True)
    lines = [
        (
            f"OK: strategy={prepared.strategy} "
            f"tokens {prepared.tokens_before}->{prepared.tokens_after} "
            "key_fact_kept=True graph_saw_summary=True"
        ),
        f"摘要消息：{summary_message.content!r}",
        "裁剪后消息序列：",
    ]
    lines += [
        f"  - [{m.type}] {str(m.content)[:60]}{'…' if len(str(m.content)) > 60 else ''}"
        for m in prepared.messages
    ]
    (out_dir / "summary.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(lines[0])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
