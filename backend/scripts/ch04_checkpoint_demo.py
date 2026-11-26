#!/usr/bin/env python3
# 第 04 篇最小闭环：中断后从 checkpoint 恢复，消息不丢不乱序。
# 第一轮写入 sqlite checkpoint → 模拟进程重启（重置检查点单例、重开同一个库、
# 重建一张新图）→ 第二轮由新图从 checkpoint 恢复完整历史。结果写 tmp/ch04/resume.txt。

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

_OUT_DIR = Path(__file__).resolve().parents[1] / "tmp" / "ch04"
os.environ["MYAF_CHECKPOINTER"] = "sqlite"
os.environ["MYAF_CHECKPOINT_SQLITE_PATH"] = str(_OUT_DIR / "checkpoints.sqlite")

from langchain_core.messages import AIMessage, HumanMessage
from myagentflow.agents.checkpointer import provider
from myagentflow.agents.lead_agent.graph import build_graph


class CountingModel:
    """离线替身模型：回答里带上本轮看到的历史条数，用于验证恢复。"""

    def __init__(self) -> None:
        self.seen: list[list] = []

    def bind_tools(self, schemas):
        del schemas
        return self

    def invoke(self, messages, *_args, **_kwargs):
        self.seen.append(list(messages))
        return AIMessage(content=f"收到（本轮看到 {len(messages)} 条消息）")


def main() -> int:
    _OUT_DIR.mkdir(parents=True, exist_ok=True)
    provider.reset_checkpointer()
    checkpointer = provider.get_checkpointer()

    thread_id = f"demo-{int(time.time())}"
    config = {"configurable": {"thread_id": thread_id}}

    # 第一轮：正常对话，结果写入 sqlite checkpoint
    model_turn1 = CountingModel()
    out1 = build_graph(model_turn1, checkpointer).invoke(
        {"messages": [HumanMessage(content="我的项目代号是青鸟")]}, config
    )
    round1 = [str(m.content) for m in out1["messages"]]

    # —— 模拟进程重启：同一个 sqlite 文件，全新的检查点实例与图 ——
    provider.reset_checkpointer()
    model_turn2 = CountingModel()
    graph_turn2 = build_graph(model_turn2, provider.get_checkpointer())
    out2 = graph_turn2.invoke(
        {"messages": [HumanMessage(content="我的项目代号是什么？")]}, config
    )

    types = [m.type for m in out2["messages"]]
    contents = [str(m.content) for m in out2["messages"]]
    seen_types = [m.type for m in model_turn2.seen[0]]
    checks = {
        "round1_persisted": round1
        == ["我的项目代号是青鸟", "收到（本轮看到 1 条消息）"],
        "history_restored": seen_types == ["human", "ai", "human"],
        "nothing_lost": contents[0] == "我的项目代号是青鸟",
        "order_kept": types == ["human", "ai", "human", "ai"],
    }
    failed = [name for name, ok in checks.items() if not ok]
    if failed:
        print(f"FAILED: {failed}", file=sys.stderr)
        return 1

    lines = [
        (
            f"OK: resumed=True messages={len(out2['messages'])} "
            f"order={','.join(types)} history_seen_by_new_graph={len(model_turn2.seen[0])}"
        ),
        f"thread_id={thread_id}",
        "恢复后的消息序列：",
    ]
    lines += [f"  - [{t}] {c}" for t, c in zip(types, contents)]
    (_OUT_DIR / "resume.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(lines[0])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
