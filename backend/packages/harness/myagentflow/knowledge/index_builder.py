"""一、文件说明
    规则式索引文本：生成文档摘要、给每个块加索引行，并决定喂给 embedding 的文本。
    为什么用规则而不是 LLM：索引文本只负责「让检索更容易命中」，确定性规则可测试、无成本。

二、目录结构
    packages/harness/myagentflow/knowledge/
    ├── __init__.py
    ├── parser.py  文件 → 纯文本
    ├── chunker.py  纯文本 → 带字符区间的块
    ├── wiki_chunker.py  按标题结构切块
    └── index_builder.py  ← 本文件：文档摘要与块索引文本

三、关键方法
    build_document_summary()   返回文档摘要与摘要索引串。
    enrich_chunk_indexes()     给每个块补 index_text 与 metadata_json。
    embedding_text_for_chunk() 决定向量化时喂「索引行 + 正文」还是只喂正文。
"""

from __future__ import annotations

import json
import re


def build_document_summary(text: str, *, file_name: str = "") -> tuple[str, str]:
    """返回 ``(summary_text, summary_index)``；标题优先取一级标题，否则用文件名。"""
    raw = (text or "").strip()
    if not raw:
        return "", file_name or "空文档"

    title = file_name or "文档"
    first_block = re.split(r"\n\n+", raw, maxsplit=1)[0].strip()
    first_line = first_block.split("\n", 1)[0].strip()
    if first_line.startswith("#"):
        title = first_line.lstrip("#").strip() or title

    summary_parts: list[str] = [title]
    body_preview = first_block[:600].strip()
    if body_preview and body_preview != title:
        summary_parts.append(body_preview)
    summary_text = "\n\n".join(summary_parts)[:1200]
    keywords = _extract_keywords(raw, limit=12)
    summary_index = " · ".join([title, *keywords[:8]]) if keywords else title
    return summary_text, summary_index


def enrich_chunk_indexes(chunks: list[dict], *, file_name: str = "") -> list[dict]:
    """给每个块补 ``index_text`` 与 ``metadata_json``；不修改传入列表。"""
    out: list[dict] = []
    for index, chunk in enumerate(chunks):
        heading = str(
            chunk.get("heading_path")
            or chunk.get("title")
            or file_name
            or f"段落 {index + 1}"
        )
        keywords = _extract_keywords(chunk.get("content") or "", limit=6)
        index_text = " · ".join([heading, *keywords]) if keywords else heading
        meta = {
            "heading_path": heading,
            "index_text": index_text,
            "title": chunk.get("title") or "",
            "kind": "section",
        }
        enriched = dict(chunk)
        enriched["index_text"] = index_text
        enriched["metadata_json"] = json.dumps(meta, ensure_ascii=False)
        out.append(enriched)
    return out


def embedding_text_for_chunk(chunk: dict) -> str:
    """向量化文本：索引行不在正文里时拼在正文前，帮助专有名词与章节名命中。"""
    index_text = str(chunk.get("index_text") or "").strip()
    content = str(chunk.get("content") or "").strip()
    if index_text and index_text not in content:
        return f"{index_text}\n\n{content}"
    return content


def summary_vector_chunk_id(file_id: str) -> str:
    """文档摘要块的稳定 id；用前缀区分正文块。"""
    return f"summary_{file_id}"


def _extract_keywords(text: str, *, limit: int = 8) -> list[str]:
    """提取中文连续词与英文标识符，去重后截断；只作索引提示，不追求分词精度。"""
    tokens = re.findall(r"[\u4e00-\u9fff]{2,}|[A-Za-z][A-Za-z0-9_-]{2,}", text or "")
    seen: set[str] = set()
    out: list[str] = []
    for token in tokens:
        key = token.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(token)
        if len(out) >= limit:
            break
    return out
