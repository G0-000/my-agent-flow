"""04.1 / 01.2：聊天回读消息表 + 会话/消息只读接口。

覆盖三件事：
1. 检查点为空时，消息表能回填历史，模型不会「失忆」；
2. 会话列表与消息分页游标可用；
3. 两套事实源不一致时只告警，不阻断回答。
"""

from __future__ import annotations

import json
import logging
from typing import Any, ClassVar

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult


class RecordingModel(BaseChatModel):
    calls: ClassVar[list[list[BaseMessage]]] = []

    @property
    def _llm_type(self) -> str:
        return "recording"

    def bind_tools(self, tools: Any, **kwargs: Any) -> RecordingModel:
        del tools, kwargs
        return self

    def _reply(self, messages: list[BaseMessage]) -> str:
        self.calls.append(list(messages))
        return f"回答{len(self.calls)}"

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        del stop, run_manager, kwargs
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content=self._reply(messages)))])

    def _stream(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: Any = None,
        **kwargs: Any,
    ):
        del stop, run_manager, kwargs
        for ch in self._reply(messages):
            yield ChatGenerationChunk(message=AIMessageChunk(content=ch))


def _sse_text(response) -> str:
    parts = []
    for line in response.text.splitlines():
        if line.startswith("data:"):
            data = json.loads(line[5:].strip())
            if "text" in data:
                parts.append(data["text"])
    return "".join(parts)


def _prepare(monkeypatch, tmp_path):
    monkeypatch.setenv("MYAF_DB_PATH", str(tmp_path / "chat.sqlite"))
    monkeypatch.setenv("MYAF_CHECKPOINTER", "memory")
    monkeypatch.setenv("MYAF_CHECKPOINT_SQLITE_PATH", str(tmp_path / "checkpoints.sqlite"))

    from myagentflow.agents.checkpointer import reset_checkpointer
    from myagentflow.persistence import db

    db.reset_db()
    reset_checkpointer()
    RecordingModel.calls = []


def test_chat_seeds_history_from_message_table(monkeypatch, tmp_path):
    _prepare(monkeypatch, tmp_path)

    from myagentflow.persistence.chat_message_repositories import append_message
    from myagentflow.persistence.session_repositories import upsert_session_row

    upsert_session_row("t-read", title="旧会话")
    append_message("t-read", "user", "旧问题")
    append_message("t-read", "assistant", "旧回答")

    model = RecordingModel()
    monkeypatch.setattr("myagentflow.models.factory.create_chat_model", lambda: model)

    from fastapi.testclient import TestClient

    from app.gateway.main import create_app

    client = TestClient(create_app())
    response = client.post("/api/chat", json={"thread_id": "t-read", "text": "新问题"})
    assert response.status_code == 200
    assert _sse_text(response) == "回答1"

    seen = [str(getattr(m, "content", "")) for m in model.calls[0]]
    assert "旧问题" in seen
    assert "旧回答" in seen
    assert "新问题" in seen
    # 回填不能把本轮 user 消息重复一次
    assert seen.count("新问题") == 1

    from myagentflow.agents.checkpointer import reset_checkpointer
    from myagentflow.persistence import db

    db.reset_db()
    reset_checkpointer()


def test_sessions_and_message_pagination(monkeypatch, tmp_path):
    _prepare(monkeypatch, tmp_path)

    from myagentflow.persistence.chat_message_repositories import append_message
    from myagentflow.persistence.session_repositories import upsert_session_row

    upsert_session_row("t-page", title="分页会话")
    for i in range(5):
        append_message("t-page", "user" if i % 2 == 0 else "assistant", f"m{i}")

    from fastapi.testclient import TestClient

    from app.gateway.main import create_app

    client = TestClient(create_app())

    sessions = client.get("/api/sessions").json()
    assert any(s["session_key"] == "t-page" for s in sessions["sessions"])

    first = client.get("/api/sessions/t-page/messages", params={"limit": 2}).json()
    assert [m["seq"] for m in first["messages"]] == [4, 5]
    assert first["next_before_seq"] == 4

    older = client.get(
        "/api/sessions/t-page/messages",
        params={"limit": 2, "before_seq": first["next_before_seq"]},
    ).json()
    assert [m["seq"] for m in older["messages"]] == [2, 3]

    missing = client.get("/api/sessions/nope/messages")
    assert missing.status_code == 404

    from myagentflow.agents.checkpointer import reset_checkpointer
    from myagentflow.persistence import db

    db.reset_db()
    reset_checkpointer()


def test_consistency_mismatch_logs_but_does_not_block(monkeypatch, tmp_path, caplog):
    _prepare(monkeypatch, tmp_path)

    from langchain_core.messages import AIMessage

    from app.gateway.routers.chat import _log_consistency

    with caplog.at_level(logging.WARNING):
        _log_consistency("t-x", [AIMessage(content="图里")], [AIMessage(content="表里")])
    assert "mismatch" in caplog.text

    from myagentflow.agents.checkpointer import reset_checkpointer
    from myagentflow.persistence import db

    db.reset_db()
    reset_checkpointer()


def test_history_limit_from_config(monkeypatch, tmp_path):
    """chat.history_limit 进配置：_history_from_table 缺省按配置条数回读。"""
    _prepare(monkeypatch, tmp_path)

    from myagentflow.config.app_config import (
        AppConfig,
        get_app_config,
        reset_app_config,
        set_app_config,
    )
    from myagentflow.config.chat_config import ChatConfig
    from myagentflow.persistence.chat_message_repositories import append_message

    from app.gateway.routers.chat import _history_from_table

    for i in range(4):
        append_message("t-limit", "user" if i % 2 == 0 else "assistant", f"m{i}")

    get_app_config()  # 先建立缓存路径，set_app_config 的注入才能被读到
    set_app_config(AppConfig(chat=ChatConfig(history_limit=2)))
    try:
        rows = _history_from_table("t-limit")
        assert [m.content for m in rows] == ["m2", "m3"]
        set_app_config(AppConfig())
        assert len(_history_from_table("t-limit")) == 4
    finally:
        reset_app_config()

    from myagentflow.agents.checkpointer import reset_checkpointer
    from myagentflow.persistence import db

    db.reset_db()
    reset_checkpointer()
