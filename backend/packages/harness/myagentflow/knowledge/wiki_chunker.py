"""一、文件说明
    Wiki 式切块：先按 Markdown 标题切章节，再把过小的相邻章节合并，超长章节才走窗口切。
    为什么单独一层：用户上传的是有结构的文档，按标题切能让检索结果带回「属于哪一节」。

二、目录结构
    packages/harness/myagentflow/knowledge/
    ├── __init__.py
    ├── parser.py  文件 → 纯文本
    ├── chunker.py  纯文本 → 带字符区间的块
    ├── wiki_chunker.py  ← 本文件：按标题结构切块
    └── index_builder.py  文档摘要与块索引文本

三、关键方法
    auto_chunk_document()      Markdown/纯文本入口；返回带 heading_path 的块。
    _split_markdown_sections() 按 # 标题切段，并用标题栈维护层级路径。
    _merge_small_sections()    合并过小章节，避免一个标题只产出一句话的块。
"""

from __future__ import annotations

import re

from myagentflow.knowledge.chunker import _count_tokens, chunk_text

_MAX_SECTION_TOKENS = 900
_MIN_SECTION_TOKENS = 120
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$", re.MULTILINE)


def auto_chunk_document(text: str, *, file_name: str = "") -> list[dict]:
    """按文档结构切块，返回兼容 ``chunk_text`` 的字段并额外带 ``heading_path``。"""
    raw = (text or "").strip()
    if not raw:
        return []

    is_markdown = (
        file_name.lower().endswith(".md") or _HEADING_RE.search(raw) is not None
    )
    sections = (
        _split_markdown_sections(raw) if is_markdown else _split_plain_sections(raw)
    )
    merged = _merge_small_sections(sections)

    chunks: list[dict] = []
    for section in merged:
        content = section["content"].strip()
        if not content:
            continue
        chunks.append(
            {
                "content": content,
                "token_count": _count_tokens(content),
                "char_start": section["start"],
                "char_end": section["end"],
                "heading_path": section.get("heading_path")
                or section.get("title")
                or file_name
                or "正文",
                "title": section.get("title") or "",
                "index_text": "",
            }
        )
    if chunks:
        return chunks

    legacy = chunk_text(raw, chunk_size=512, overlap=50)
    for item in legacy:
        item["heading_path"] = file_name or "正文"
        item["title"] = ""
        item["index_text"] = ""
    return legacy


def _split_markdown_sections(text: str) -> list[dict]:
    """按 # 标题切段；heading_path 用标题栈拼成 ``一级 / 二级``。"""
    matches = list(_HEADING_RE.finditer(text))
    if not matches:
        return _split_plain_sections(text)

    sections: list[dict] = []
    heading_stack: list[tuple[int, str]] = []
    for index, match in enumerate(matches):
        level = len(match.group(1))
        title = match.group(2).strip()
        start = match.start()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)

        while heading_stack and heading_stack[-1][0] >= level:
            heading_stack.pop()
        heading_stack.append((level, title))
        path = " / ".join(heading for _, heading in heading_stack)
        body = text[match.end() : end].strip()
        content = (
            f"{match.group(0).strip()}\n\n{body}".strip()
            if body
            else match.group(0).strip()
        )
        sections.append(
            {
                "start": start,
                "end": end,
                "title": title,
                "heading_path": path,
                "content": content,
                "tokens": _count_tokens(content),
            }
        )

    prefix = text[: matches[0].start()].strip()
    if prefix:
        sections.insert(
            0,
            {
                "start": 0,
                "end": matches[0].start(),
                "title": "概述",
                "heading_path": "概述",
                "content": prefix,
                "tokens": _count_tokens(prefix),
            },
        )
    return sections


def _split_plain_sections(text: str) -> list[dict]:
    """没有标题时按空行切段，首行作为这一段的标题。"""
    sections: list[dict] = []
    cursor = 0
    for part in re.split(r"\n\n+", text):
        stripped = part.strip()
        if not stripped:
            cursor += len(part) + 2
            continue
        start = text.find(stripped, cursor)
        end = start + len(stripped)
        title = stripped.split("\n", 1)[0][:48]
        sections.append(
            {
                "start": start,
                "end": end,
                "title": title,
                "heading_path": title,
                "content": stripped,
                "tokens": _count_tokens(stripped),
            }
        )
        cursor = end
    return sections


def _merge_small_sections(sections: list[dict]) -> list[dict]:
    """合并相邻小章节；超长章节再交给 ``chunk_text`` 做重叠窗口切。"""
    if not sections:
        return []

    merged: list[dict] = []
    buffer: dict | None = None

    def flush() -> None:
        nonlocal buffer
        if buffer:
            merged.append(buffer)
            buffer = None

    for section in sections:
        tokens = int(section.get("tokens") or _count_tokens(section["content"]))
        if tokens > _MAX_SECTION_TOKENS:
            flush()
            merged.append(section)
            continue
        if buffer is None:
            buffer = dict(section)
            continue
        combined = int(buffer.get("tokens") or 0) + tokens
        if combined <= _MAX_SECTION_TOKENS:
            buffer["content"] = f"{buffer['content']}\n\n{section['content']}".strip()
            buffer["end"] = section["end"]
            buffer["tokens"] = combined
            if buffer.get("title") != section.get("title") and section.get("title"):
                buffer["heading_path"] = (
                    f"{buffer.get('heading_path', '')} / {section.get('title', '')}".strip(
                        " /"
                    )
                )
        else:
            flush()
            buffer = dict(section)
    flush()

    out: list[dict] = []
    for section in merged:
        if _count_tokens(section["content"]) <= _MAX_SECTION_TOKENS:
            out.append(section)
            continue
        for piece in chunk_text(
            section["content"], chunk_size=_MAX_SECTION_TOKENS, overlap=40
        ):
            out.append(
                {
                    "start": section["start"] + piece["char_start"],
                    "end": section["start"] + piece["char_end"],
                    "title": section.get("title") or "",
                    "heading_path": section.get("heading_path")
                    or section.get("title")
                    or "正文",
                    "content": piece["content"],
                    "tokens": piece["token_count"],
                }
            )
    return out
