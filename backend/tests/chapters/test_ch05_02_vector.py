from __future__ import annotations


def test_top1(tmp_path):
    from myagentflow.knowledge.vector_store import VectorStore

    s = VectorStore(tmp_path / "v.sqlite")
    s.add("d1", "A", "猫", [1.0, 0.0])
    s.add("d1", "B", "狗", [0.0, 1.0])
    top = s.search([1.0, 0.0], top_k=1)[0]
    assert top["text"] == "猫" and abs(top["score"] - 1.0) < 1e-6
