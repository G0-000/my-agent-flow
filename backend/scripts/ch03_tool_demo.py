#!/usr/bin/env python3
# 第 03 篇最小闭环：模型发起工具调用 → 执行 → 结果回灌 → 最终回答。
# 离线替身模型先发起一次 echo 调用，图把 ToolMessage 回灌后给出最终回答；
# ToolExecutor 挂 AuditMiddleware 留审计。结果写 tmp/ch03/tool.txt。

from __future__ import annotations

import sys
from pathlib import Path

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from myagentflow.agents.lead_agent.graph import build_graph
from myagentflow.agents.middlewares.audit import AuditMiddleware
from myagentflow.tools.builtins.echo import register_echo
from myagentflow.tools.executor import ToolExecutor
from myagentflow.tools.registry import ToolRegistry

TOOL_TEXT = "你好，回声"
FINAL_ANSWER = f"已通过 echo 工具回声：{TOOL_TEXT}"


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
    executor = ToolExecutor(registry, [AuditMiddleware()])
    model = ToolCallingModel()

    graph = build_graph(model, tools=registry, tool_executor=executor)
    out = graph.invoke(
        {"messages": [HumanMessage(content=f"请用 echo 工具发送：{TOOL_TEXT}")]}
    )

    tool_messages = [m for m in out["messages"] if isinstance(m, ToolMessage)]
    final = str(out["messages"][-1].content)
    checks = {
        "model_called_then_answered": model.calls == 2,
        "tool_result_backfilled": bool(tool_messages)
        and str(tool_messages[0].content) == TOOL_TEXT,
        "final_answer": final == FINAL_ANSWER,
        "message_flow": [m.type for m in out["messages"]]
        == ["human", "ai", "tool", "ai"],
    }
    failed = [name for name, ok in checks.items() if not ok]
    if failed:
        print(f"FAILED: {failed}", file=sys.stderr)
        return 1

    out_dir = Path(__file__).resolve().parents[1] / "tmp" / "ch03"
    out_dir.mkdir(parents=True, exist_ok=True)
    lines = [
        f"OK: tool=echo result={TOOL_TEXT} rounds={model.calls} final={final}",
        "闭环步骤：",
        "  1. 模型发起 tool_calls（echo）",
        "  2. tools 节点经 ToolExecutor + AuditMiddleware 执行",
        f"  3. ToolMessage 回灌：{tool_messages[0].content}",
        f"  4. 最终回答：{final}",
    ]
    (out_dir / "tool.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(lines[0])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
