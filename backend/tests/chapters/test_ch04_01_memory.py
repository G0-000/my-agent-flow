from __future__ import annotations


def test_fail_soft(tmp_path):
    from myagentflow.memory.agent_memory import AgentMemoryManager

    m = AgentMemoryManager(tmp_path)
    path = m.thread_path("t1")
    path.parent.mkdir(parents=True)
    path.write_text("{bad json", encoding="utf-8")
    assert m.load_thread("t1") == {"facts": [], "context": {}}


def test_scopes_are_separate(tmp_path):
    from myagentflow.memory.agent_memory import AgentMemoryManager

    m = AgentMemoryManager(tmp_path)
    m.remember("t1", "只属于这个线程")
    m.remember("t1", "跨任务偏好", scope="agent")
    assert m.load_thread("t1")["facts"] == ["只属于这个线程"]
    assert m.load_agent()["facts"] == ["跨任务偏好"]
