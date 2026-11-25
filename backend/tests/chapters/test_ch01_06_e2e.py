"""一、文件说明
    第 1 部分验收：模型 → 图 → 消息落库 → SSE 串成一条链。

二、覆盖
    EchoModel()        假模型：不联网，只回显；测试里所有模型都该这样替身。
    test_end_to_end()  模型回复落库后按角色读回，SSE 首帧带 id。

三、运行
    uv run pytest tests/chapters/test_ch01_06_e2e.py -q
"""

from __future__ import annotations

from langchain_core.messages import AIMessage, HumanMessage


class EchoModel:
    """假模型：不联网，只回显；测试里所有模型都该这样替身。"""

    def invoke(self, messages, *_a, **_k):
        """同步回显最后一条消息；不联网、不引入模型依赖。"""
        return AIMessage(content="echo: " + messages[-1].content)


def test_end_to_end(monkeypatch, tmp_path):
    """模型回复落库后按角色读回，SSE 首帧带 id。"""
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
