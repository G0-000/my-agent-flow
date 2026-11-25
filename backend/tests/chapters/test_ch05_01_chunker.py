"""一、文件说明
    第 5 部分第 1 章：文件解析、纯文本切块、标题切块与索引文本。

二、覆盖
    test_parse_text_and_reject_unknown()        文本/Markdown 解析与未知扩展名报错。
    test_chunk_text_keeps_offsets_and_overlap() 段落装箱、字符区间与重叠。
    test_auto_chunk_document_keeps_heading()    Markdown 标题路径进入块。
    test_index_builder_summary_and_enrich()     摘要、索引行与 embedding 文本。

    test_parse_docx_and_pptx()                  stdlib 解包 Office 正文与幻灯片。

三、运行
    uv run pytest tests/chapters/test_ch05_01_chunker.py -q
"""

from __future__ import annotations

import zipfile

from myagentflow.knowledge.chunker import chunk_text
from myagentflow.knowledge.index_builder import (
    build_document_summary,
    embedding_text_for_chunk,
    enrich_chunk_indexes,
)
from myagentflow.knowledge.parser import parse_file
from myagentflow.knowledge.wiki_chunker import auto_chunk_document


def test_parse_text_and_reject_unknown(tmp_path):
    """Markdown 能读出原文；未知二进制扩展名要明确报错。"""
    doc = tmp_path / "note.md"
    doc.write_text("# 标题\n\n正文", encoding="utf-8")
    assert parse_file(doc) == "# 标题\n\n正文"

    binary = tmp_path / "photo.bin"
    binary.write_bytes(b"\x00\x01")
    try:
        parse_file(binary)
    except ValueError as exc:
        assert "Unsupported file type" in str(exc)
    else:  # pragma: no cover - 只要不报错就说明白名单漏了
        raise AssertionError("unknown extension should fail")


def test_chunk_text_keeps_offsets_and_overlap():
    """每块字符区间落在原文内；超长段落切出的块保留重叠。"""
    text = "短段一。\n\n" + ("这是很长的一段。" * 1200)
    chunks = chunk_text(text, chunk_size=120, overlap=20)
    assert len(chunks) > 1
    for chunk in chunks:
        assert 0 <= chunk["char_start"] <= chunk["char_end"] <= len(text)
        assert chunk["token_count"] > 0
    overlapped = any(
        chunks[index]["content"][-20:] in chunks[index + 1]["content"]
        for index in range(len(chunks) - 1)
    )
    assert overlapped


def test_auto_chunk_document_keeps_heading():
    """Markdown 的 heading_path 不能丢；块正文要带标题。"""
    text = "# 安装\n\n先装依赖。\n\n## 验证\n\n跑一遍测试。"
    chunks = auto_chunk_document(text, file_name="guide.md")
    assert chunks
    assert chunks[0]["heading_path"].startswith("安装")
    assert "安装" in chunks[0]["content"]


def test_index_builder_summary_and_enrich():
    """摘要取标题，块索引行包含 heading，embedding 文本把索引行拼在正文前。"""
    summary, summary_index = build_document_summary(
        "# 部署\n\n使用 uvicorn 启动。", file_name="deploy.md"
    )
    assert "部署" in summary
    assert "部署" in summary_index

    chunks = enrich_chunk_indexes(
        [
            {
                "content": "使用 uvicorn 启动服务",
                "heading_path": "部署 / 启动",
                "token_count": 8,
            }
        ],
        file_name="deploy.md",
    )
    assert chunks[0]["index_text"].startswith("部署 / 启动")
    assert chunks[0]["index_text"] in embedding_text_for_chunk(chunks[0])


def test_parse_docx_and_pptx(tmp_path):
    """docx/pptx 不依赖 Office 运行时，直接解 XML 取正文。"""
    docx = tmp_path / "note.docx"
    with zipfile.ZipFile(docx, "w") as archive:
        archive.writestr(
            "word/document.xml",
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            "<w:body><w:p><w:r><w:t>你好</w:t></w:r></w:p></w:body></w:document>",
        )
    assert parse_file(docx) == "你好"

    pptx = tmp_path / "slides.pptx"
    with zipfile.ZipFile(pptx, "w") as archive:
        archive.writestr(
            "ppt/slides/slide1.xml",
            '<p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" '
            'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">'
            "<p:cSld><p:spTree><a:t>第一页</a:t></p:spTree></p:cSld></p:sld>",
        )
    assert "第一页" in parse_file(pptx)
