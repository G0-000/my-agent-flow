"""R0 端到端：HTTP /api/chat → 流式模型 → checkpointer → 消息归档。"""

from __future__ import annotations

import json
from typing import Any, ClassVar

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult


class StreamingE2EModel(BaseChatModel):
    """真实 LangChain ChatModel 替身：按字符流式输出，并记录每次看到的上下文。"""

    calls: ClassVar[list[list[BaseMessage]]] = []

    @property
    def _llm_type(self) -> str:
        return "e2e-stream"

    def bind_tools(self, tools: Any, **kwargs: Any) -> StreamingE2EModel:
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
    """把 token 事件里的文本拼回来；SSE 每帧是独立 JSON。"""
    parts = []
    for line in response.text.splitlines():
        if not line.startswith("data:"):
            continue
        data = json.loads(line[5:].strip())
        if "text" in data:
            parts.append(data["text"])
    return "".join(parts)


def test_http_chat_streams_and_second_turn_sees_history(monkeypatch, tmp_path):
    monkeypatch.setenv("MYAF_DB_PATH", str(tmp_path / "chat.sqlite"))
    monkeypatch.setenv("MYAF_CHECKPOINTER", "memory")
    monkeypatch.setenv("MYAF_CHECKPOINT_SQLITE_PATH", str(tmp_path / "checkpoints.sqlite"))

    from fastapi.testclient import TestClient
    from myagentflow.agents.checkpointer import reset_checkpointer
    from myagentflow.persistence import db

    db.reset_db()
    reset_checkpointer()

    model = StreamingE2EModel()
    monkeypatch.setattr("myagentflow.models.factory.create_chat_model", lambda: model)

    from app.gateway.main import create_app

    client = TestClient(create_app())
    first = client.post("/api/chat", json={"thread_id": "t-e2e", "text": "ping"})
    assert first.status_code == 200
    assert "event: done" in first.text
    assert _sse_text(first) == "回答1"

    second = client.post("/api/chat", json={"thread_id": "t-e2e", "text": "再来"})
    assert second.status_code == 200
    assert _sse_text(second) == "回答2"

    # 第二轮模型必须看到第一轮的用户消息与回答，证明 checkpointer 真带历史。
    assert any(getattr(m, "content", "") == "ping" for m in model.calls[1])
    assert any(getattr(m, "content", "") == "回答1" for m in model.calls[1])

    from myagentflow.persistence.chat_message_repositories import list_messages

    roles = [m["role"] for m in list_messages("t-e2e")]
    assert roles == ["user", "assistant", "user", "assistant"]
    db.reset_db()
    reset_checkpointer()
