"""05.4：抽取队列接上聊天入口与后台 worker。

覆盖：
- 一轮问答结束后入队；空回答不入队
- worker.tick 真能抽取、写回并 ack
- start 幂等，stop 后线程退出
- /api/chat 的 on_final 会入队（HTTP 路径，不是只测模块）
"""

from __future__ import annotations

import json
from typing import Any, ClassVar

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, AIMessageChunk
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult


class ExtractModel:
    def __init__(self, payload: Any):
        self.payload = payload

    def invoke(self, *_a, **_kw):
        body = self.payload if isinstance(self.payload, str) else json.dumps(self.payload)
        return AIMessage(content=body)


class StreamModel(BaseChatModel):
    calls: ClassVar[int] = 0

    @property
    def _llm_type(self) -> str:
        return "stream"

    def bind_tools(self, tools: Any, **kwargs: Any) -> StreamModel:
        del tools, kwargs
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs) -> ChatResult:
        del messages, stop, run_manager, kwargs
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content="记一下"))])

    def _stream(self, messages, stop=None, run_manager=None, **kwargs):
        del messages, stop, run_manager, kwargs
        for ch in "记一下":
            yield ChatGenerationChunk(message=AIMessageChunk(content=ch))


def _reset_worker(monkeypatch, tmp_path):
    monkeypatch.setenv("MYAF_MEMORY_DB", str(tmp_path / "memory.sqlite"))
    monkeypatch.setenv("MYAF_DB_PATH", str(tmp_path / "chat.sqlite"))
    monkeypatch.setenv("MYAF_CHECKPOINTER", "memory")

    from myagentflow.memory import worker

    worker.stop_worker()
    worker.reset_queue()


def test_enqueue_exchange_skips_empty_and_merges():
    from myagentflow.memory import worker

    worker.reset_queue()
    assert worker.enqueue_exchange("user:u1", "t1", "问题", "   ") is None
    assert worker.get_queue().pending_count() == 0

    worker.enqueue_exchange("user:u1", "t1", "问题一", "回答一")
    worker.enqueue_exchange("user:u1", "t1", "问题二", "回答二")
    assert worker.get_queue().pending_count() == 1


def test_worker_tick_writes_atoms_and_acks(monkeypatch, tmp_path):
    _reset_worker(monkeypatch, tmp_path)

    from myagentflow.memory import facade, worker
    from myagentflow.memory.namespaces import user_ns

    ns = user_ns("u1")
    item = worker.enqueue_exchange(ns, "t1", "我在写 my-agent-flow", "收到，记下了")
    assert item is not None
    item.due_at = 0  # 跳过防抖，模拟到期

    model = ExtractModel([
        {
            "content": "用户正在写 my-agent-flow 的 Agent 运行时",
            "layer": "semantic",
            "kind": "fact",
            "confidence": 0.9,
            "subject_key": "project:my-agent-flow",
        }
    ])
    w = worker.MemoryWorker(lambda: model, interval=60, queue=worker.get_queue())
    stats = w.tick(now=10)

    assert stats["processed"] == 1
    assert stats["written"] == 1
    assert worker.get_queue().pending_count() == 0
    hits = facade.recall([ns], "my-agent-flow 运行时")
    assert any("my-agent-flow" in h["content"] for h in hits)


def test_worker_start_is_idempotent_and_stops(monkeypatch, tmp_path):
    _reset_worker(monkeypatch, tmp_path)

    from myagentflow.memory import worker

    w = worker.MemoryWorker(lambda: ExtractModel("[]"), interval=60)
    assert w.start() is True
    assert w.start() is False
    w.stop()
    assert w._thread is None


def test_chat_final_enqueues_memory(monkeypatch, tmp_path):
    _reset_worker(monkeypatch, tmp_path)

    from myagentflow.agents.checkpointer import reset_checkpointer
    from myagentflow.persistence import db

    db.reset_db()
    reset_checkpointer()

    monkeypatch.setattr("myagentflow.models.factory.create_chat_model", lambda: StreamModel())

    from fastapi.testclient import TestClient

    from app.gateway.main import create_app

    client = TestClient(create_app())
    response = client.post("/api/chat", json={"thread_id": "t-mem", "text": "你好"})
    assert response.status_code == 200

    from myagentflow.memory import worker

    assert worker.get_queue().pending_count() == 1

    db.reset_db()
    reset_checkpointer()
    worker.reset_queue()


def test_worker_interval_defaults_to_config(monkeypatch, tmp_path):
    """interval 缺省读 config.yaml 的 memory.worker_interval；显式传参优先。"""
    _reset_worker(monkeypatch, tmp_path)

    from myagentflow.config.app_config import (
        AppConfig,
        get_app_config,
        reset_app_config,
        set_app_config,
    )
    from myagentflow.config.memory_config import MemoryConfig
    from myagentflow.memory import worker

    get_app_config()  # 先建立缓存路径，set_app_config 的注入才能被读到
    try:
        set_app_config(AppConfig(memory=MemoryConfig(worker_interval=1.5)))
        w = worker.MemoryWorker(lambda: None, queue=worker.get_queue())
        assert w.interval == 1.5
        set_app_config(AppConfig())
        w2 = worker.MemoryWorker(lambda: None, queue=worker.get_queue())
        assert w2.interval == 5.0
        w3 = worker.MemoryWorker(lambda: None, interval=60, queue=worker.get_queue())
        assert w3.interval == 60
    finally:
        reset_app_config()
