"""第 05.2 章：召回、快照与注入的最小行为测试。"""

from __future__ import annotations


def test_memory_context_formats_standing_and_archival(monkeypatch, tmp_path):
    monkeypatch.setenv("MYAF_MEMORY_DB", str(tmp_path / "memory.sqlite"))
    from myagentflow.memory import facade, recall_snapshot
    from myagentflow.memory.injection import build_memory_context
    from myagentflow.memory.namespaces import user_ns

    ns = user_ns("u1")
    facade.remember(
        ns,
        "用户偏好简短的中文回答",
        kind="preference",
        subject_key="response_style",
        importance=0.9,
        confidence=0.9,
        source="user",
        pin=True,
    )

    block = build_memory_context([ns], "中文回答", thread_id="t1")

    assert "<memory>" in block
    assert "<memory_archival>" in block
    assert "简短的中文回答" in block
    snap = recall_snapshot.get_thread_recall("t1")
    assert snap["hit_count"] >= 1


def test_memory_context_empty_when_no_namespace():
    from myagentflow.memory.injection import build_memory_context

    assert build_memory_context([], "任意") == ""
