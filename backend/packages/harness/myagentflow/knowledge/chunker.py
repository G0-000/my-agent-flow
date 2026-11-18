"""一、文件说明
    切块：先按标题分段，再按窗口滑。
    为什么保留标题路径：检索命中一段后，模型需要知道「这段属于哪一章」，
    否则会把某个小节的结论当全局结论。

二、目录结构
    packages/harness/myagentflow/knowledge/
    ├── __init__.py
    ├── chunker.py  ← 本文件
    ├── map.py  知识地图：文档 → 标题 → 块 id。
    └── vector_store.py  向量存储：SQLite + Python 余弦。

三、关键方法
    Chunk
    _split_sections()
    chunk_text()
"""
from __future__ import annotations

import re
from dataclasses import dataclass

# 只认 1–6 级标题（跳过代码块里的 # 由调用方处理）；分组编号给「按标题切块」用
_HEADING = re.compile(r"^(#{1,6})\s+(.*)$", re.MULTILINE)


@dataclass(frozen=True)
class Chunk:
    text: str
    heading: str
    index: int


def _split_sections(text: str) -> list[tuple[str, str]]:
    sections: list[tuple[str, str]] = []
    current_heading = ""
    buf: list[str] = []
    for line in text.splitlines():
        m = _HEADING.match(line)
        if m:
            if buf:
                sections.append((current_heading, "\n".join(buf).strip()))
            current_heading = m.group(2).strip()
            buf = []
        else:
            buf.append(line)
    if buf:
        sections.append((current_heading, "\n".join(buf).strip()))
    return [(h, b) for h, b in sections if b]


def chunk_text(text: str, max_chars: int = 800, overlap: int = 80) -> list[Chunk]:
    chunks: list[Chunk] = []
    idx = 0
    for heading, body in _split_sections(text):
        if len(body) <= max_chars:
            chunks.append(Chunk(body, heading, idx)); idx += 1
            continue
        step = max(1, max_chars - overlap)      # 步长 = 窗口 - 重叠
        for start in range(0, len(body), step):
            piece = body[start:start + max_chars]
            if not piece.strip():
                continue
            chunks.append(Chunk(piece, heading, idx)); idx += 1
    return chunks
