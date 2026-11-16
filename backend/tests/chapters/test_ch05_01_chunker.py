from __future__ import annotations


def test_overlap_covers_text():
    from myagentflow.knowledge.chunker import chunk_text

    body = "".join(str(i % 10) for i in range(1500))
    chunks = chunk_text("# T\n" + body, max_chars=400, overlap=50)
    assert len(chunks) > 1
    assert all(c.heading == "T" for c in chunks)
    # 每块起点都在原文里，且相邻块有重叠
    assert chunks[0].text[-50:] == chunks[1].text[:50]


def test_heading_inherited():
    from myagentflow.knowledge.chunker import chunk_text

    cs = chunk_text("# A\nbody a\n## B\nbody b")
    assert [c.heading for c in cs] == ["A", "B"]
