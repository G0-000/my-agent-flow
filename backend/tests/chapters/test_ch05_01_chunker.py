"""一、文件说明
    05/01 切片：长度切分、重叠与标题继承。

二、覆盖
    test_overlap_covers_text()  长文切成多块，每块继承标题，相邻块 50 字符重叠。
    test_heading_inherited()    标题切换后，各块归属自己的标题。

三、运行
    uv run pytest tests/chapters/test_ch05_01_chunker.py -q
"""

from __future__ import annotations


def test_overlap_covers_text():
    """长文切成多块，每块继承标题，相邻块 50 字符重叠。"""
    from myagentflow.knowledge.chunker import chunk_text

    body = "".join(str(i % 10) for i in range(1500))
    chunks = chunk_text("# T\n" + body, max_chars=400, overlap=50)
    assert len(chunks) > 1
    assert all(c.heading == "T" for c in chunks)
    # 每块起点都在原文里，且相邻块有重叠
    assert chunks[0].text[-50:] == chunks[1].text[:50]


def test_heading_inherited():
    """标题切换后，各块归属自己的标题。"""
    from myagentflow.knowledge.chunker import chunk_text

    cs = chunk_text("# A\nbody a\n## B\nbody b")
    assert [c.heading for c in cs] == ["A", "B"]
