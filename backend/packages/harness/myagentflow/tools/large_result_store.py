"""一、文件说明
    超大工具结果落盘：超过阈值就写文件，模型只拿信封（大小 + 路径 + 预览）。
    为什么不直接截断：截断后的内容找不回来；落盘后模型可以再用 read 按需取。

二、目录结构
    packages/harness/myagentflow/tools/
    ├── builtins/
    ├── host_direct/
    ├── large_result_store.py  ← 本文件
    ├── registry.py
    └── tool_output_truncation.py

三、关键方法
    _get_store_dir()                  落盘目录：$MYAF_DATA_DIR/large_tool_results。
    _prune_old_files()                清掉超过 24h 的旧文件，避免无限增长。
    build_head_summary()              头部摘要：前若干行 + 总字符/行数。
    format_decimal_bytes()            人类可读大小（B/KB/MB/GB）。
    is_persisted_output_content()     判断内容是否已经是信封，避免二次包装。
    maybe_persist()                   超阈值时落盘并返回信封，否则原样返回。
"""
from __future__ import annotations

import hashlib
import logging
import os
import time
from pathlib import Path

logger = logging.getLogger(__name__)

_PERSISTED_DIR_NAME = "large_tool_results"
# 超过 10K 字符才落盘：低于这个量直接内联，落盘反而多一次磁盘往返
THRESHOLD_CHARS = 10_000
# 旧文件保留 24h：排查当天问题够用，又不至于把磁盘吃满
MAX_AGE_HOURS = 24
SUMMARY_HEAD_LINES = 20
SUMMARY_MAX_CHARS = 2_000
_PERSISTED_OUTPUT_OPEN_TAG = "<persisted-output>"
_PERSISTED_OUTPUT_CLOSE_TAG = "</persisted-output>"
_PERSISTED_OUTPUT_PREVIEW_CHARS = 2_000


def _get_store_dir() -> Path:
    """落盘目录：$MYAF_DATA_DIR/large_tool_results。"""
    base = Path(os.environ.get("MYAF_DATA_DIR") or (Path.home() / ".myagentflow"))
    store_dir = base / _PERSISTED_DIR_NAME
    store_dir.mkdir(parents=True, exist_ok=True)
    return store_dir


def _prune_old_files(store_dir: Path) -> None:
    """清掉超过 24h 的旧文件，避免无限增长。"""
    cutoff = time.time() - MAX_AGE_HOURS * 3600
    for f in store_dir.iterdir():
        if f.is_file() and f.stat().st_mtime < cutoff:
            try:
                f.unlink()
            except OSError:
                pass


def build_head_summary(content: str) -> str:
    """头部摘要：前若干行 + 总字符/行数。"""
    lines = content.splitlines()
    head = "\n".join(lines[:SUMMARY_HEAD_LINES])
    if len(head) > SUMMARY_MAX_CHARS:
        head = head[:SUMMARY_MAX_CHARS] + "…"
    return f"{head}\n… ({len(content):,} chars, {len(lines):,} lines total)"


def format_decimal_bytes(num: int) -> str:
    """人类可读大小（B/KB/MB/GB）。"""
    if num < 1_000:
        return f"{num} B"
    if num < 1_000_000:
        return f"{round(num / 1_000)} KB"
    if num < 1_000_000_000:
        return f"{round(num / 1_000_000)} MB"
    return f"{round(num / 1_000_000_000)} GB"


def _preview_first_chars(content: str, max_chars: int) -> tuple[str, bool]:
    """头部预览；尽量在换行处截断，避免半个单词/半个 JSON。"""
    if len(content) <= max_chars:
        return content, False
    newline_index = content.rfind("\n", 0, max_chars)
    end = newline_index if newline_index > max_chars * 0.5 else max_chars
    return content[:end], True


def is_persisted_output_content(content: str) -> bool:
    """判断内容是否已经是信封，避免二次包装。"""
    text = (content or "").strip()
    return text.startswith(_PERSISTED_OUTPUT_OPEN_TAG) and _PERSISTED_OUTPUT_CLOSE_TAG in text


def _format_persisted_output_envelope(
    *,
    tool_name: str,
    content: str,
    original_chars: int,
    persisted_path: str,
) -> str:
    """拼 zcode 风格信封：原始大小、全量路径、头部预览、按需读取提示。"""
    del tool_name  # 当前信封不展示工具名；文件名里已经带了
    preview, has_more = _preview_first_chars(content, _PERSISTED_OUTPUT_PREVIEW_CHARS)
    lines = [
        _PERSISTED_OUTPUT_OPEN_TAG,
        (
            f"Output too large ({format_decimal_bytes(original_chars)} chars). "
            f"Full output saved to: {persisted_path}"
        ),
        "",
        f"Preview (first {format_decimal_bytes(_PERSISTED_OUTPUT_PREVIEW_CHARS)}):",
        preview,
    ]
    if has_more:
        lines.append("...")
    lines.append(_PERSISTED_OUTPUT_CLOSE_TAG)
    lines.append("")
    lines.append(f"Use read with path='{persisted_path}' and offset/limit for on-demand loading.")
    return "\n".join(lines)


def maybe_persist(
    content: str,
    tool_name: str,
    tool_call_id: str,
    *,
    thread_id: str | None = None,
) -> str:
    """超阈值时落盘并返回信封，否则原样返回。

    文件名 = 工具名 + tool_call_id + 内容哈希前 12 位：
    同一调用重放会命中同一文件，不同内容不会互相覆盖。
    """
    del thread_id  # 上下文引用登记（context_ref_lru）尚未实现
    n = len(content)
    if n <= THRESHOLD_CHARS or is_persisted_output_content(content):
        return content

    content_hash = hashlib.md5(content.encode("utf-8")).hexdigest()[:12]
    safe_name = tool_name.replace("/", "_").replace(" ", "_")
    filename = f"{safe_name}_{tool_call_id}_{content_hash}.txt"
    store_dir = _get_store_dir()
    filepath = store_dir / filename

    try:
        _prune_old_files(store_dir)
        filepath.write_text(content, encoding="utf-8")
        logger.info("Persisted large tool result (%d chars) to %s", n, filepath)
        return _format_persisted_output_envelope(
            tool_name=tool_name,
            content=content,
            original_chars=n,
            persisted_path=str(filepath),
        )
    except OSError as exc:
        logger.warning("Failed to persist large tool result to %s: %s", filepath, exc)
        return content[:SUMMARY_MAX_CHARS] + f"\n\n… [persist failed, total {n:,} chars]"
