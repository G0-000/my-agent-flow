"""一、文件说明
    05/03 知识地图：按文档/章节聚合与摘要截断。

二、覆盖
    test_map_and_describe()  地图按文档/章节聚合块号，摘要受 max_docs 限制。

三、运行
    uv run pytest tests/chapters/test_ch05_03_map.py -q
"""

from __future__ import annotations


def test_map_and_describe():
    """地图按文档/章节聚合块号，摘要受 max_docs 限制。"""
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
