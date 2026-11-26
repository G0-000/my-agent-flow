"""05.5：工具产物登记到图状态，并能从检查点读回。

覆盖：
- 写文件工具 → 产物进 ThreadState.artifacts
- 输出里的 http(s) 链接 → url 产物
- 普通正文里的路径不登记（避免噪声）
- 只读检查点能取回产物（前端接口的数据源）
"""

from __future__ import annotations

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage


class WriteFileModel:
    def __init__(self) -> None:
        self.calls = 0

    def bind_tools(self, schemas):
        del schemas
        return self

    def invoke(self, messages, *_a, **_kw):
        self.calls += 1
        if any(isinstance(m, ToolMessage) for m in messages):
            return AIMessage(content="写好了")
        return AIMessage(
            content="",
            tool_calls=[
                {"name": "write_file", "args": {"path": "notes/out.md", "content": "hi"}, "id": "c1"}
            ],
        )


def test_collect_write_file_and_url():
    from myagentflow.artifacts.collect import collect_artifacts

    files = collect_artifacts("write_file", {"path": "a/b.md"}, "written: /x/a/b.md (2 chars)")
    assert files and files[0]["type"] == "file"
    assert files[0]["path"] == "a/b.md"

    urls = collect_artifacts("echo", {}, "see https://example.com/x for details")
    assert any(u["type"] == "url" and u["url"] == "https://example.com/x" for u in urls)

    assert collect_artifacts("echo", {}, "普通正文 /tmp/not-an-artifact") == []


def test_graph_registers_artifacts(monkeypatch, tmp_path):
    monkeypatch.setenv("MYAF_WORKSPACE", str(tmp_path / "ws"))

    from langgraph.checkpoint.memory import InMemorySaver
    from myagentflow.agents.checkpointer.thread_state_reader import read_thread_state
    from myagentflow.agents.lead_agent.graph import build_graph
    from myagentflow.tools.builtins.workspace_files import register_workspace_files
    from myagentflow.tools.registry import ToolRegistry

    registry = ToolRegistry()
    register_workspace_files(registry)
    saver = InMemorySaver()
    graph = build_graph(WriteFileModel(), saver, tools=registry)

    out = graph.invoke(
        {"messages": [HumanMessage(content="写文件")]},
        {"configurable": {"thread_id": "t-art"}},
    )

    assert out["messages"][-1].content == "写好了"
    assert "notes/out.md" in out["artifacts"]
    assert out["artifacts"]["notes/out.md"]["type"] == "file"
    assert (tmp_path / "ws" / "notes" / "out.md").read_text() == "hi"

    snapshot = read_thread_state(saver, "t-art")
    assert snapshot is not None
    assert "notes/out.md" in snapshot["values"]["artifacts"]
