from __future__ import annotations


def test_append_and_history(tmp_path):
    from myagentflow.persistence.messages import MessageStore

    store = MessageStore(tmp_path / "m.sqlite")
    assert store.append("a", "user", "1") == 1
    assert store.append("a", "assistant", "2") == 2
    assert store.append("b", "user", "x") == 1        # 另一个线程从 1 开始

    assert [m["content"] for m in store.history("a")] == ["1", "2"]
    assert len(store.history("a", limit=1)) == 1
