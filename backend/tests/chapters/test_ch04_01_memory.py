"""第 4 部分第 1 章：短期/长期记忆、命名空间、原子表、门面、召回快照。"""

from __future__ import annotations

import pytest
from myagentflow.agents.memory.agent_memory import (
    AgentMemoryManager,
    get_agent_memory_manager,
)
from myagentflow.config.paths import get_paths, reset_paths_cache
from myagentflow.memory import facade, recall_snapshot, store
from myagentflow.memory.namespaces import agent_ns, parse_namespace, user_ns


@pytest.fixture()
def data_dir(tmp_path, monkeypatch):
    """每个用例独立数据目录；记忆库也指到临时目录，避免污染 ~/.myagentflow。"""
    monkeypatch.setenv("MYAF_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("MYAF_MEMORY_DB", str(tmp_path / "memory.sqlite"))
    reset_paths_cache()
    yield tmp_path
    reset_paths_cache()


def test_paths_and_agent_memory_roundtrip(data_dir):
    """路径由 base_dir 推导；agent/task 两层记忆各写各的，互不覆盖。"""
    paths = get_paths()
    assert paths.base_dir == data_dir
    manager = AgentMemoryManager("Planner")
    manager.save_agent_memory(
        {"facts": [{"text": "偏好简洁"}], "context": {"lang": "zh"}}
    )
    assert paths.agent_memory_file("planner").exists()
    assert manager.load_agent_memory()["context"]["lang"] == "zh"

    manager.add_to_task_history("thread-1", "user", "你好")
    task = manager.load_task_memory("thread-1")
    assert task["conversation_history"][0]["content"] == "你好"
    combined = manager.get_combined_memory("thread-1")
    assert combined["agent_memory"]["facts"][0]["text"] == "偏好简洁"
    assert combined["task_memory"]["conversation_history"][0]["role"] == "user"


def test_agent_memory_manager_is_cached():
    """同名复用同一实例，避免每轮重复读盘。"""
    assert get_agent_memory_manager("planner") is get_agent_memory_manager("planner")


def test_namespaces_parse_and_prefix():
    """命名空间是「类型:归属」；解析非法时按 workspace 兜底。"""
    assert user_ns("u1") == "user:u1"
    assert agent_ns("planner") == "agent:planner"
    assert parse_namespace("user:u1") == ("user", "u1")
    assert parse_namespace("bad") == ("user", "bad")


def test_subject_key_replaces_old_value(data_dir):
    """同一 subject_key 再写会更新原行并升 revision，不堆重复事实。"""
    ns = user_ns("u1")
    first = store.upsert_atom(
        namespace_id=ns, content="喜欢喝美式", subject_key="drink"
    )
    second = store.upsert_atom(
        namespace_id=ns, content="喜欢喝拿铁", subject_key="drink"
    )
    assert first == second
    atom = store.get_atom(first)
    assert atom["content"] == "喜欢喝拿铁"
    assert atom["revision"] == 2
    assert store.count_active_atoms(ns) == 1


def test_facade_noise_filter_and_recall(data_dir):
    """低置信度噪声被丢；正常记忆可召回、可软删。"""
    ns = user_ns("u1")
    assert facade.remember(ns, "随便猜的", confidence=0.2, source="infer") is None
    aid = facade.remember(
        ns, "用户喜欢简洁回复", importance=0.9, confidence=0.9, source="user"
    )
    assert aid
    hits = facade.recall([ns], "简洁 回复")
    assert hits and hits[0]["id"] == aid
    assert facade.forget(aid) is True
    assert facade.recall([ns], "简洁") == []


def test_get_core_and_format_block(data_dir):
    """核心记忆取 pin/偏好；注入块必须带 <memory> 包裹。"""
    ns = user_ns("u1")
    facade.remember(ns, "回复用中文", kind="preference", pin=True, source="user")
    core = facade.get_core([ns])
    assert core
    block = facade.format_atoms_block(core)
    assert block.startswith("<memory>")


def test_recall_snapshot_trims_and_copies(data_dir):
    """快照只留 24 条、正文 240 字，返回副本防止调用方改内部状态。"""
    recall_snapshot.reset_for_tests()
    long = "x" * 500
    hits = [{"id": str(i), "content": long} for i in range(30)]
    recall_snapshot.record_thread_recall("t1", query="x", hits=hits)
    snap = recall_snapshot.get_thread_recall("t1")
    assert snap["hit_count"] == 24
    assert len(snap["hits"]) == 24
    assert len(snap["hits"][0]["content"]) == 240
    snap["hits"].clear()
    assert recall_snapshot.get_thread_recall("t1")["hit_count"] == 24
    recall_snapshot.clear_thread_recall("t1")
    assert recall_snapshot.get_thread_recall("t1") is None
