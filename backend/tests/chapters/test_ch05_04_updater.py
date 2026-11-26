"""第 05.4 章：记忆异步抽取与更新队列的最小行为测试。

覆盖：
- 防抖：同 namespace+thread 连续入队合并成一条，到期时间顺延
- 到期出队：due 不删，ack 才删；失败退避仍留在队列
- 抽取：JSON 围栏可解析；非法字段丢弃；空结果不写库
- 写回：flush_queue 真写进 atom，可被关键词召回
"""

from __future__ import annotations

import json

import pytest


class FakeExtractModel:
    """按脚本返回 JSON；用来验证解析与写回，不验证模型质量。"""

    def __init__(self, payload):
        self.payload = payload
        self.calls = 0

    def invoke(self, messages, *_a, **_kw):
        from langchain_core.messages import AIMessage

        self.calls += 1
        body = self.payload if isinstance(self.payload, str) else json.dumps(self.payload)
        return AIMessage(content=body)


@pytest.fixture(autouse=True)
def _memory_db(monkeypatch, tmp_path):
    monkeypatch.setenv("MYAF_MEMORY_DB", str(tmp_path / "memory.sqlite"))


def test_debounce_merges_same_thread():
    from myagentflow.memory.queue import MemoryUpdateQueue

    q = MemoryUpdateQueue(debounce_seconds=3)
    q.enqueue("user:u1", "第一轮：我在写 my-agent-flow", thread_id="t1", now=100)
    item = q.enqueue("user:u1", "第二轮：用 sqlite 做记忆", thread_id="t1", now=101)

    assert item.rounds == 1
    assert "第一轮" in item.text and "第二轮" in item.text
    assert item.due_at == 104
    assert q.due(now=103) == []
    assert [i.key for i in q.due(now=104)] == ["user:u1|t1"]


def test_ack_and_retry():
    from myagentflow.memory.queue import MemoryUpdateQueue

    q = MemoryUpdateQueue(debounce_seconds=0)
    q.enqueue("user:u1", "a", thread_id="t1", now=0)
    item = q.due(now=0)[0]

    q.fail(item)
    q.retry_later(item, delay=5, now=0)
    assert item.attempts == 1
    assert q.due(now=4) == []
    assert q.due(now=5) == [item]

    q.ack(item)
    assert q.pending_count() == 0


def test_flush_writes_atoms_and_recallable():
    from myagentflow.memory import facade, updater
    from myagentflow.memory.namespaces import user_ns
    from myagentflow.memory.queue import MemoryUpdateQueue

    ns = user_ns("u1")
    model = FakeExtractModel(
        '```json\n[{"content":"用户在复刻 my-agent-flow 的 Agent 运行时",'
        '"layer":"semantic","kind":"fact","importance":0.8,"confidence":0.9,'
        '"subject_key":"project:my-agent-flow"},'
        '{"content":"","layer":"semantic"}]\n```'
    )
    q = MemoryUpdateQueue(debounce_seconds=0)
    q.enqueue(ns, "聊了很久 my-agent-flow 的运行时", thread_id="t1", now=10)

    stats = updater.flush_queue(q, model, now=10)

    assert stats["written"] == 1 and stats["processed"] == 1
    assert q.pending_count() == 0
    hits = facade.recall([ns], "my-agent-flow 运行时")
    assert any("my-agent-flow" in h["content"] for h in hits)


def test_extract_empty_and_bad_json():
    from myagentflow.memory import updater

    assert updater.extract_atoms(FakeExtractModel("[]"), "没有值得记的内容") == []
    assert updater.extract_atoms(FakeExtractModel("这不是 JSON"), "x") == []


def test_flush_failure_keeps_item():
    from myagentflow.memory import updater
    from myagentflow.memory.queue import MemoryUpdateQueue

    class Boom:
        def invoke(self, *_a, **_kw):
            raise RuntimeError("model down")

    q = MemoryUpdateQueue(debounce_seconds=0)
    q.enqueue("user:u1", "x", thread_id="t1", now=0)
    stats = updater.flush_queue(q, Boom(), now=0)

    assert stats["failed"] == 1 and stats["processed"] == 1
    assert q.pending_count() == 1
    assert q.due(now=100)[0].attempts == 1
