from __future__ import annotations


def test_map_and_describe():
    from myagentflow.knowledge.map import build_map, describe

    items = [
        {"doc_id": "d1", "heading": "A", "chunk_id": 1},
        {"doc_id": "d1", "heading": "A", "chunk_id": 2},
        {"doc_id": "d2", "heading": "B", "chunk_id": 3},
    ]
    tree = build_map(items)
    assert tree["d1"]["A"] == [1, 2]
    assert "d1（2 块）" in describe(tree)
    assert "d2" not in describe(tree, max_docs=1)
