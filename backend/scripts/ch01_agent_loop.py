#!/usr/bin/env python3
# 第 01 篇最小 Agent 循环：模型发起工具调用 → 图执行工具 → 结果回灌 → 最终回答。
# 与 ch03 的差别：这里不加中间件与上下文管理，只保留 build_graph 的
# 「模型 ↔ 工具」最小回路，证明第 1 章的图离线即可完整闭环。结果写 tmp/ch01/agent_loop.txt。

from __future__ import annotations

import sys
from pathlib import Path

from langchain_core.messages import AIMessage, HumanMessage
from myagentflow.agents.lead_agent.graph import build_graph
from myagentflow.tools.builtins.echo import register_echo
from myagentflow.tools.executor import ToolExecutor
from myagentflow.tools.registry import ToolRegistry

TOOL_TEXT = "你好，最小 Agent"
FINAL_ANSWER = f"最小 Agent 循环完成：{TOOL_TEXT}"


class ToolCallingModel:
    """离线替身模型：第一次发起 echo 调用，第二次给出最终回答。"""

    def __init__(self) -> None:
        self.calls = 0

    def bind_tools(self, schemas):
        del schemas
        return self

    def invoke(self, messages, *_args, **_kwargs):
        self.calls += 1
        if self.calls == 1:
            return AIMessage(
                content="",
                tool_calls=[
                    {"name": "echo", "args": {"text": TOOL_TEXT}, "id": "call-1"}
                ],
            )
        return AIMessage(content=FINAL_ANSWER)


def main() -> int:
    registry = ToolRegistry()
    register_echo(registry)
    model = ToolCallingModel()

    graph = build_graph(model, tools=registry, tool_executor=ToolExecutor(registry))
    out = graph.invoke(
        {"messages": [HumanMessage(content=f"请用 echo 工具回声：{TOOL_TEXT}")]}
    )

    final = str(out["messages"][-1].content)
    types = [m.type for m in out["messages"]]
    checks = {
        "model_called_then_answered": model.calls == 2,
        "final_answer": final == FINAL_ANSWER,
        "message_flow": types == ["human", "ai", "tool", "ai"],
    }
    failed = [name for name, ok in checks.items() if not ok]
    if failed:
        print(f"FAILED: {failed}", file=sys.stderr)
        return 1

    out_dir = Path(__file__).resolve().parents[1] / "tmp" / "ch01"
    out_dir.mkdir(parents=True, exist_ok=True)
    lines = [
        f"OK: loop=human→ai(tool_calls)→tool→ai final={final}",
        f"模型调用次数：{model.calls}（1 次发起工具调用 + 1 次最终回答）",
    ]
    (out_dir / "agent_loop.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(lines[0])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
