"""一、文件说明
    纯文本切块：先按空行切段，再按 token 预算装箱，段内超长时按字符重叠硬切。
    为什么不直接按字数切：段落是作者给的语义边界，切断段落的块检索命中后上下文会缺一半。

二、目录结构
    packages/harness/myagentflow/knowledge/
    ├── __init__.py
    ├── parser.py  文件 → 纯文本
    ├── chunker.py  ← 本文件：纯文本 → 带字符区间的块
    ├── wiki_chunker.py  按标题结构切块
    └── index_builder.py  文档摘要与块索引文本

三、关键方法
    _count_tokens()     轻量 token 估算：有 tiktoken 就用，没有按 4 字符 ≈ 1 token。
    chunk_text()        段落装箱 + 相邻块重叠，返回 content/token_count/char_start/char_end。
    _split_paragraphs() 按空行切段并记录原文起止位置。
"""

from __future__ import annotations

import re
from contextlib import suppress

_tiktoken_enc = None
with suppress(Exception):  # tiktoken 是可选依赖：有就精确计数，没有不影响切块
    import tiktoken

    _tiktoken_enc = tiktoken.get_encoding("cl100k_base")


def _count_tokens(text: str) -> int:
    """估算 token 数；没有 tiktoken 时按 4 字符约 1 token。"""
    if _tiktoken_enc is not None:
        return len(_tiktoken_enc.encode(text))
    return max(1, len(text) // 4)


def chunk_text(
    text: str,
    chunk_size: int = 512,
    overlap: int = 50,
) -> list[dict]:
    """把文本切成重叠块，尽量不切断段落。

    返回的每块都带 ``char_start`` / ``char_end``，用于回答时回指原文位置。
    重叠按 token 计，内部换算成字符时使用 4 字符 ≈ 1 token 的同一套估算。
    """
    if not text or not text.strip():
        return []

    chunk_size = max(1, int(chunk_size))
    overlap = max(0, min(int(overlap), chunk_size - 1))
    paragraphs = _split_paragraphs(text)
    if not paragraphs:
        return []

    chunks: list[dict] = []
    current_parts: list[str] = []
    current_tokens = 0
    current_start = paragraphs[0]["start"]
    current_end = paragraphs[0]["end"]
    overlap_chars = overlap * 4

    for para in paragraphs:
        para_text = para["text"]
        para_tokens = _count_tokens(para_text)

        if para_tokens > chunk_size:
            if current_parts:
                chunks.append(_make_chunk(current_parts, current_start, current_end))
                current_parts = []
                current_tokens = 0

            for piece_text, piece_start, piece_end in _hard_split(
                para_text,
                chunk_size=chunk_size,
                overlap=overlap,
                base_start=para["start"],
            ):
                chunks.append(_make_chunk([piece_text], piece_start, piece_end))
            continue

        if current_tokens + para_tokens > chunk_size and current_parts:
            chunks.append(_make_chunk(current_parts, current_start, current_end))
            tail = chunks[-1]["content"][-overlap_chars:] if overlap_chars else ""
            current_parts = [tail] if tail else []
            current_tokens = _count_tokens(tail) if tail else 0
            current_start = max(0, para["start"] - len(tail))

        current_parts.append(para_text)
        current_tokens += para_tokens
        current_end = para["end"]

    if current_parts:
        chunks.append(_make_chunk(current_parts, current_start, current_end))
    return chunks


def _split_paragraphs(text: str) -> list[dict]:
    """按空行切段，返回 ``text/start/end``；位置基于原文，便于引用。"""
    result: list[dict] = []
    cursor = 0
    for part in re.split(r"(\n\s*\n)", text):
        if not part or re.fullmatch(r"\n\s*\n", part):
            cursor += len(part)
            continue
        stripped = part.strip()
        if not stripped:
            cursor += len(part)
            continue
        leading = len(part) - len(part.lstrip())
        start = cursor + leading
        result.append({"text": stripped, "start": start, "end": start + len(stripped)})
        cursor += len(part)
    if result:
        return result
    stripped = text.strip()
    start = len(text) - len(text.lstrip())
    return (
        [{"text": stripped, "start": start, "end": start + len(stripped)}]
        if stripped
        else []
    )


def _make_chunk(parts: list[str], char_start: int, char_end: int) -> dict:
    """把累计的段落拼成一个块，并补齐 token 与字符区间。"""
    content = "\n\n".join(part for part in parts if part).strip()
    return {
        "content": content,
        "token_count": _count_tokens(content),
        "char_start": max(0, int(char_start)),
        "char_end": max(0, int(char_end)),
    }


def _hard_split(
    text: str,
    *,
    chunk_size: int,
    overlap: int,
    base_start: int,
) -> list[tuple[str, int, int]]:
    """超长段落按字符窗口硬切；窗口之间保留 overlap 个 token 的重叠。"""
    window = max(1, chunk_size * 4)
    step = max(1, window - overlap * 4)
    out: list[tuple[str, int, int]] = []
    for start in range(0, len(text), step):
        piece = text[start : start + window]
        if not piece.strip():
            continue
        out.append((piece, base_start + start, base_start + start + len(piece)))
        if start + window >= len(text):
            break
    return out
