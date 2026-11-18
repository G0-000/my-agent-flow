from __future__ import annotations

from langchain_core.messages import AIMessage, HumanMessage


class EchoModel:
    def invoke(self, messages, *_a, **_k):
        return AIMessage(content="echo: " + messages[-1].content)


def test_end_to_end(monkeypatch, tmp_path):
    from myagentflow.agents.lead_agent.graph import build_graph
    from myagentflow.persistence.chat_message_repositories import (
        append_message,
        list_messages,
    )
    from myagentflow.runtime.events import EventStream
    from myagentflow.tools.builtins.echo import register_echo
    from myagentflow.tools.registry import ToolRegistry

    monkeypatch.setenv("MYAF_DB_PATH", str(tmp_path / "e2e.sqlite"))
    from myagentflow.persistence import db
    db.reset_db()
    registry = ToolRegistry()
    register_echo(registry)

    graph = build_graph(EchoModel())
    append_message("t1", "user", "你好")
    out = graph.invoke({"messages": [HumanMessage(content="你好")]})

    append_message("t1", "assistant", out["messages"][-1].content)
    history = list_messages("t1")
    assert [m["role"] for m in history] == ["user", "assistant"]

    sse = EventStream().emit("done").to_sse()
    assert sse.startswith("id: 1") and sse.endswith("\n\n")
    assert registry.call("echo", {"text": "x"}) == "x"
