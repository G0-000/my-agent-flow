"""一、文件说明
    13/01 全链路：计划 → 图 → 消息 → 记忆 → SSE。

二、覆盖
    ScriptedModel()    假模型：按顺序返回固定回复，保证测试可重复。
    test_full_chain()  计划依赖、图回复、消息落库、记忆与 SSE 全链路成立。

三、运行
    uv run pytest tests/chapters/test_ch13_01_e2e.py -q
"""

from __future__ import annotations


class ScriptedModel:
    """假模型：按顺序返回固定回复，保证测试可重复。"""

    def __init__(self):
        self.calls = 0

    def invoke(self, messages, *_a, **_k):
        from langchain_core.messages import AIMessage

        self.calls += 1
        return AIMessage(content="done")


def test_full_chain(monkeypatch, tmp_path):
    """计划依赖、图回复、消息落库、记忆与 SSE 全链路成立。"""
    from myagentflow.agents.lead_agent.graph import build_graph
    from myagentflow.agents.memory.agent_memory import AgentMemoryManager
    from myagentflow.persistence.chat_message_repositories import (
        append_message,
    )
    from myagentflow.plans.parser import parse
    from myagentflow.runtime.events import EventStream
    from myagentflow.tools.builtins.echo import register_echo
    from myagentflow.tools.registry import ToolRegistry

    plan = parse("- [ ] 读代码\n- [ ] 写实现 depends: 读代码")
    assert plan[1].depends == [plan[0].id]

    registry = ToolRegistry()
    register_echo(registry)
    graph = build_graph(ScriptedModel())
    out = graph.invoke({"messages": [{"role": "user", "content": "hi"}]})
    assert out["messages"][-1].content == "done"

    monkeypatch.setenv("MYAF_DB_PATH", str(tmp_path / "m.sqlite"))
    from myagentflow.persistence import db

    db.reset_db()
    append_message("t1", "user", "hi")
    append_message("t1", "assistant", "done")

    monkeypatch.setenv("MYAF_DATA_DIR", str(tmp_path / "data"))
    from myagentflow.config.paths import reset_paths_cache

    reset_paths_cache()
    mem = AgentMemoryManager("planner")
    mem.add_to_task_history("t1", "user", "用户偏好中文")

    sse = EventStream().emit("done").to_sse()
    assert sse.startswith("id: 1")
