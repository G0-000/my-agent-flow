"""一、文件说明
    05/02 向量检索：余弦相似度取 top-1。

二、覆盖
    test_top1()  检索返回余弦最相似的一条，分数为 1.0。

三、运行
    uv run pytest tests/chapters/test_ch05_02_vector.py -q
"""

from __future__ import annotations


def test_top1(tmp_path):
    """检索返回余弦最相似的一条，分数为 1.0。"""
    from myagentflow.knowledge.vector_store import VectorStore

    s = VectorStore(tmp_path / "v.sqlite")
    s.add("d1", "A", "猫", [1.0, 0.0])
    s.add("d1", "B", "狗", [0.0, 1.0])
    top = s.search([1.0, 0.0], top_k=1)[0]
    assert top["text"] == "猫" and abs(top["score"] - 1.0) < 1e-6
