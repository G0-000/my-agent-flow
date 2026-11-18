"""一、文件说明
    04/01 记忆：坏文件容错与 agent/thread 作用域隔离。

二、覆盖
    test_fail_soft()            记忆文件是坏 JSON 时返回空记忆，不让流程崩。
    test_scopes_are_separate()  thread 记忆与 agent 记忆互不混。

三、运行
    uv run pytest tests/chapters/test_ch04_01_memory.py -q
"""

from __future__ import annotations


def test_fail_soft(tmp_path):
    """记忆文件是坏 JSON 时返回空记忆，不让流程崩。"""
    from myagentflow.memory.agent_memory import AgentMemoryManager

    m = AgentMemoryManager(tmp_path)
    path = m.thread_path("t1")
    path.parent.mkdir(parents=True)
    path.write_text("{bad json", encoding="utf-8")
    assert m.load_thread("t1") == {"facts": [], "context": {}}


def test_scopes_are_separate(tmp_path):
    """thread 记忆与 agent 记忆互不混。"""
    from myagentflow.memory.agent_memory import AgentMemoryManager

    m = AgentMemoryManager(tmp_path)
    m.remember("t1", "只属于这个线程")
    m.remember("t1", "跨任务偏好", scope="agent")
    assert m.load_thread("t1")["facts"] == ["只属于这个线程"]
    assert m.load_agent()["facts"] == ["跨任务偏好"]
