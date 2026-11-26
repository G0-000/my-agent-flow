"""第 04.3 章：聊天流收尾与消息归档的最小行为测试。"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

from myagentflow.runtime.streaming import stream_graph


class FakeGraph:
    async def astream_events(self, payload, config, version):
        del payload, config, version
        yield {
            "event": "on_chat_model_stream",
            "data": {"chunk": SimpleNamespace(content="你")},
        }
        yield {
            "event": "on_chat_model_stream",
            "data": {"chunk": SimpleNamespace(content="好")},
        }
        yield {"event": "on_tool_end", "name": "echo", "data": {"output": "x"}}


class ErrorGraph:
    async def astream_events(self, payload, config, version):
        del payload, config, version
        raise RuntimeError("boom")
        yield  # pragma: no cover


def test_stream_graph_calls_on_final_after_tokens():
    got: list[str] = []
    chunks: list[str] = []

    async def run() -> None:
        async for chunk in stream_graph(
            FakeGraph(),
            {"messages": []},
            {"configurable": {"thread_id": "t"}},
            on_final=got.append,
        ):
            chunks.append(chunk)

    asyncio.run(run())

    assert got == ["你好"]
    assert "event: done" in chunks[-1]


def test_stream_graph_stops_when_cancelled():
    cancelled: list[str] = []
    checks = iter([False, True])

    async def run() -> None:
        async for _ in stream_graph(
            FakeGraph(),
            {"messages": []},
            {"configurable": {"thread_id": "t"}},
            should_cancel=lambda: next(checks, True),
            on_cancel=lambda: cancelled.append("yes"),
        ):
            pass

    asyncio.run(run())

    assert cancelled == ["yes"]


def test_stream_graph_calls_on_error_instead_of_final():
    got: list[str] = []

    async def run() -> None:
        async for _ in stream_graph(
            ErrorGraph(),
            {"messages": []},
            {"configurable": {"thread_id": "t"}},
            on_error=got.append,
        ):
            pass

    asyncio.run(run())

    assert got == ["boom"]


def test_chat_safe_append_archives_without_breaking(monkeypatch, tmp_path):
    from myagentflow.persistence import db
    from myagentflow.persistence.chat_message_repositories import list_messages
    from myagentflow.persistence.session_repositories import get_session_row_for_ui

    from app.gateway.routers.chat import _safe_append

    monkeypatch.setenv("MYAF_DB_PATH", str(tmp_path / "chat.sqlite"))
    db.reset_db()
    _safe_append("t1", "user", "你好")

    assert list_messages("t1")[0]["content"] == "你好"
    assert get_session_row_for_ui("t1")["title"] == "你好"
    db.reset_db()
