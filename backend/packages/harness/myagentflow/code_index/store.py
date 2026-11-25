"""一、文件说明
    工作区代码索引：索引文件、符号表、FTS 全文表与内部调用引用，查询时合并三路结果。
    为什么 FTS + 符号表并存：符号名精确命中要准，注释/字符串里的关键词又要能搜到，单靠一路会漏。

二、目录结构
    packages/harness/myagentflow/code_index/
    ├── __init__.py
    ├── tokenize.py  轻量分词
    ├── symbols.py  符号抽取
    ├── import_bindings.py  import 别名
    ├── internal_refs.py  内部调用引用
    ├── store.py  ← 本文件：索引与查询
    └── format_results.py  结果转文本

三、关键方法
    index_file()    增量索引一个文件；删除或忽略文件时清掉旧行。
    build_index()   扫描工作区并全量重建。
    search_index()  符号 + FTS + 引用三路合并，返回 hits 与 internal_ref_users。
"""

from __future__ import annotations

import re
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from myagentflow.code_index.internal_refs import extract_internal_refs
from myagentflow.code_index.symbols import extract_symbols
from myagentflow.code_index.tokenize import build_fts_aux_text, tokens_from_text

CODE_INDEX_REL_DIR = Path(".myaf") / "code_index"
CODE_INDEX_DB_NAME = "index.db"
_MAX_FILE_BYTES = 2 * 1024 * 1024
_MAX_FILES = 2000
_SKIP_DIRS = {
    ".git",
    ".hg",
    ".svn",
    ".myaf",
    ".venv",
    "venv",
    "__pycache__",
    "node_modules",
    "dist",
    "build",
    ".mypy_cache",
    ".pytest_cache",
}
_SOURCE_SUFFIXES = {
    ".py",
    ".pyi",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".java",
    ".go",
    ".rs",
    ".c",
    ".h",
    ".cpp",
    ".hpp",
    ".cs",
    ".rb",
    ".php",
    ".swift",
    ".kt",
    ".kts",
    ".scala",
    ".sh",
}


def resolve_index_root(
    workspace_root: str | Path | None = None,
    *,
    thread_id: str | None = None,
) -> str:
    """确定工作区根；显式 root 优先，否则用当前目录，thread_id 只作为隔离目录名。"""
    if workspace_root:
        return str(Path(workspace_root).expanduser().resolve())
    if thread_id:
        return str((Path.cwd() / ".myaf" / "threads" / str(thread_id)).resolve())
    return str(Path.cwd().resolve())


def index_db_path(
    workspace_root: str | Path | None = None, *, thread_id: str | None = None
) -> str:
    """索引库路径：``{root}/.myaf/code_index/index.db``。"""
    root = Path(resolve_index_root(workspace_root, thread_id=thread_id))
    return str(root / CODE_INDEX_REL_DIR / CODE_INDEX_DB_NAME)


def index_file(
    workspace_root: str | Path | None = None,
    *,
    relative_path: str,
    thread_id: str | None = None,
    deleted: bool = False,
) -> dict[str, Any]:
    """增量索引一个文件；deleted=True 或文件消失时只做删除。"""
    root = Path(resolve_index_root(workspace_root, thread_id=thread_id))
    rel = _normalize_rel(relative_path)
    path = root / rel
    with _connect(root) as conn:
        return _index_one(conn, root, rel, path, deleted=deleted)


def build_index(
    workspace_root: str | Path | None = None,
    *,
    thread_id: str | None = None,
    max_files: int = _MAX_FILES,
) -> dict[str, Any]:
    """全量扫描并索引；每个文件独立写入，单个文件失败不拖垮整批。"""
    root = Path(resolve_index_root(workspace_root, thread_id=thread_id))
    indexed = 0
    skipped = 0
    failed: list[str] = []
    with _connect(root) as conn:
        for rel, path in _iter_source_files(root, max_files=max_files):
            try:
                result = _index_one(conn, root, rel, path)
                if result["action"] == "indexed":
                    indexed += 1
                else:
                    skipped += 1
            except Exception as exc:
                failed.append(f"{rel}: {exc}")
                skipped += 1
        _touch_meta(conn, "last_full_build")
    return {
        "root": str(root),
        "dbPath": index_db_path(root),
        "indexed": indexed,
        "skipped": skipped,
        "failed": failed,
    }


def search_index(
    workspace_root: str | Path | None = None,
    query: str = "",
    *,
    queries: list[str] | None = None,
    thread_id: str | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    """查符号、全文与内部引用；query/queries 合并成一个检索词集合。"""
    root = Path(resolve_index_root(workspace_root, thread_id=thread_id))
    db_file = Path(index_db_path(root))
    terms: list[str] = []
    seen: set[str] = set()
    for item in [query, *(queries or [])]:
        for token in _query_terms(str(item or "")):
            key = token.casefold()
            if key not in seen:
                seen.add(key)
                terms.append(token)
    if not terms or not db_file.exists():
        return {"query": query, "hits": [], "internal_ref_users": [], "total": 0}

    with _connect(root) as conn:
        hits = _search_symbols(conn, terms)
        hits.extend(_search_fts(conn, terms))
        refs = _search_refs(conn, terms)
        grouped: dict[tuple[str, int, str], dict[str, Any]] = {}
        for hit in hits:
            key = (str(hit["path"]), int(hit.get("line") or 0), str(hit["kind"]))
            if key not in grouped or hit.get("score", 0) > grouped[key].get("score", 0):
                grouped[key] = hit
        final_hits = sorted(
            grouped.values(),
            key=lambda item: (-item.get("score", 0), item["path"], item.get("line", 0)),
        )
        return {
            "query": query,
            "hits": final_hits[: max(1, int(limit))],
            "internal_ref_users": refs,
            "total": len(final_hits),
        }


def index_status(
    workspace_root: str | Path | None = None,
    *,
    thread_id: str | None = None,
) -> dict[str, Any]:
    """返回索引是否存在、文件/符号/引用数量与最后构建时间。"""
    root = Path(resolve_index_root(workspace_root, thread_id=thread_id))
    db_file = Path(index_db_path(root))
    if not db_file.exists():
        return {
            "root": str(root),
            "dbPath": str(db_file),
            "exists": False,
            "files": 0,
            "symbols": 0,
            "refs": 0,
        }
    with _connect(root) as conn:
        files = conn.execute(
            "SELECT COUNT(DISTINCT path) AS c FROM symbols"
        ).fetchone()["c"]
        symbols = conn.execute("SELECT COUNT(*) AS c FROM symbols").fetchone()["c"]
        refs = conn.execute("SELECT COUNT(*) AS c FROM internal_refs").fetchone()["c"]
        meta = conn.execute(
            "SELECT value FROM meta WHERE key = 'last_full_build'"
        ).fetchone()
    return {
        "root": str(root),
        "dbPath": str(db_file),
        "exists": True,
        "files": int(files),
        "symbols": int(symbols),
        "refs": int(refs),
        "lastFullBuild": meta["value"] if meta else "",
    }


@contextmanager
def _connect(root: Path) -> Iterator[sqlite3.Connection]:
    """打开索引库并确保 schema 存在；退出时关闭连接。"""
    db_file = Path(index_db_path(root))
    db_file.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_file), timeout=30.0)
    conn.row_factory = sqlite3.Row
    try:
        _ensure_schema(conn)
        yield conn
    finally:
        conn.close()


def _ensure_schema(conn: sqlite3.Connection) -> None:
    """建符号表、FTS5 全文表、引用表与 meta 表。"""
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS symbols (
            path TEXT NOT NULL,
            name TEXT NOT NULL,
            kind TEXT NOT NULL,
            line INTEGER NOT NULL,
            end_line INTEGER NOT NULL,
            signature TEXT NOT NULL DEFAULT '',
            container TEXT NOT NULL DEFAULT ''
        );
        CREATE INDEX IF NOT EXISTS idx_symbols_name ON symbols(name);
        CREATE INDEX IF NOT EXISTS idx_symbols_path ON symbols(path);

        CREATE VIRTUAL TABLE IF NOT EXISTS fts_content USING fts5(
            path UNINDEXED,
            content
        );

        CREATE TABLE IF NOT EXISTS internal_refs (
            from_path TEXT NOT NULL,
            to_path TEXT NOT NULL,
            line INTEGER NOT NULL,
            ref_kind TEXT NOT NULL,
            symbol TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_refs_symbol ON internal_refs(symbol);

        CREATE TABLE IF NOT EXISTS meta (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        """
    )
    conn.commit()


def _index_one(
    conn: sqlite3.Connection,
    root: Path,
    rel: str,
    path: Path,
    *,
    deleted: bool = False,
) -> dict[str, Any]:
    """单文件索引：先清旧行，再写符号、引用与 FTS。"""
    _delete_path(conn, rel)
    if deleted or not path.exists() or not _should_index_file(path):
        _touch_meta(conn, "last_index_change")
        conn.commit()
        return {"path": rel, "action": "deleted"}

    text = path.read_text(encoding="utf-8", errors="replace")
    symbols = extract_symbols(root, rel, text)
    refs = extract_internal_refs(root, rel, text)

    for symbol in symbols:
        conn.execute(
            """
            INSERT INTO symbols(path, name, kind, line, end_line, signature, container)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                rel,
                symbol["name"],
                symbol["kind"],
                int(symbol["line"]),
                int(symbol.get("end_line") or symbol["line"]),
                str(symbol.get("signature") or ""),
                str(symbol.get("container") or ""),
            ),
        )
    for ref in refs:
        conn.execute(
            """
            INSERT INTO internal_refs(from_path, to_path, line, ref_kind, symbol)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                ref["from_path"],
                ref["to_path"],
                int(ref["line"]),
                ref["ref_kind"],
                ref["symbol"],
            ),
        )
    conn.execute(
        "INSERT INTO fts_content(path, content) VALUES (?, ?)",
        (rel, build_fts_aux_text(path=rel, symbols=symbols, text=text)),
    )
    _touch_meta(conn, "last_index_change")
    conn.commit()
    return {
        "path": rel,
        "action": "indexed",
        "symbols": len(symbols),
        "refs": len(refs),
    }


def _delete_path(conn: sqlite3.Connection, rel: str) -> None:
    """删掉某路径在符号、引用、FTS 中的全部旧行。"""
    conn.execute("DELETE FROM symbols WHERE path = ?", (rel,))
    conn.execute("DELETE FROM internal_refs WHERE from_path = ?", (rel,))
    conn.execute("DELETE FROM fts_content WHERE path = ?", (rel,))


def _iter_source_files(root: Path, *, max_files: int) -> list[tuple[str, Path]]:
    """深度优先扫描源码；跳过依赖/缓存目录与超大文件。"""
    out: list[tuple[str, Path]] = []
    if not root.exists():
        return out
    for path in root.rglob("*"):
        if len(out) >= max_files:
            break
        if not path.is_file():
            continue
        rel_parts = path.relative_to(root).parts
        if any(part in _SKIP_DIRS for part in rel_parts):
            continue
        if not _should_index_file(path):
            continue
        out.append((path.relative_to(root).as_posix(), path))
    return out


def _should_index_file(path: Path) -> bool:
    """扩展名在白名单内、文件不超 2MB 才索引。"""
    if path.suffix.lower() not in _SOURCE_SUFFIXES:
        return False
    try:
        return path.stat().st_size <= _MAX_FILE_BYTES
    except OSError:
        return False


def _normalize_rel(relative_path: str) -> str:
    """相对路径归一化，拒绝逃出工作区。"""
    raw = str(relative_path or "").replace("\\", "/").lstrip("/")
    parts = [part for part in raw.split("/") if part and part != "."]
    if not parts or any(part == ".." for part in parts):
        raise ValueError(f"unsafe relative path: {relative_path}")
    return "/".join(parts)


def _query_terms(text: str) -> list[str]:
    """单标识符保留完整名字，避免 ``old_name`` 被拆成 old/name 后误命中 ``new_name``。"""
    raw = text.strip()
    if re.fullmatch(r"[A-Za-z_$][A-Za-z0-9_$]{1,}", raw):
        return [raw]
    return tokens_from_text(raw)


def _search_symbols(conn: sqlite3.Connection, terms: list[str]) -> list[dict[str, Any]]:
    """符号表打分：精确 100、前缀 85、包含 70、签名 40、路径 20。"""
    rows = conn.execute(
        "SELECT path, name, kind, line, end_line, signature, container FROM symbols"
    ).fetchall()
    lowered_terms = [term.casefold() for term in terms]
    hits: list[dict[str, Any]] = []
    for row in rows:
        name = str(row["name"])
        name_lower = name.casefold()
        score = 0
        for term in lowered_terms:
            if name_lower == term:
                score = max(score, 100)
            elif name_lower.startswith(term):
                score = max(score, 85)
            elif term in name_lower:
                score = max(score, 70)
            elif term in str(row["signature"]).casefold():
                score = max(score, 40)
            elif term in str(row["path"]).casefold():
                score = max(score, 20)
        if score:
            hits.append(
                {
                    "path": row["path"],
                    "line": int(row["line"]),
                    "endLine": int(row["end_line"]),
                    "kind": "symbol",
                    "symbolKind": row["kind"],
                    "name": name,
                    "signature": row["signature"],
                    "container": row["container"],
                    "score": score,
                }
            )
    return hits


def _search_fts(conn: sqlite3.Connection, terms: list[str]) -> list[dict[str, Any]]:
    """FTS 全文查询；查询词全部加引号，避免用户输入被当成 FTS 语法。"""
    escaped = [term.replace('"', '""') for term in terms[:10]]
    match_query = " OR ".join(f'"{term}"' for term in escaped)
    rows = conn.execute(
        """
        SELECT path, snippet(fts_content, 1, '', '', '…', 16) AS snip, bm25(fts_content) AS rank
        FROM fts_content
        WHERE fts_content MATCH ?
        ORDER BY rank
        LIMIT 40
        """,
        (match_query,),
    ).fetchall()
    hits: list[dict[str, Any]] = []
    for row in rows:
        rank = abs(float(row["rank"] or 0))
        hits.append(
            {
                "path": row["path"],
                "line": 1,
                "kind": "content",
                "snippet": re.sub(r"\s+", " ", str(row["snip"] or "")).strip(),
                "score": max(10, 60 - rank),
            }
        )
    return hits


def _search_refs(conn: sqlite3.Connection, terms: list[str]) -> list[dict[str, Any]]:
    """查内部引用：symbol 精确或前缀命中，返回 who-calls 列表。"""
    rows = conn.execute(
        "SELECT from_path, to_path, line, ref_kind, symbol FROM internal_refs ORDER BY from_path, line"
    ).fetchall()
    lowered = [term.casefold() for term in terms]
    out: list[dict[str, Any]] = []
    for row in rows:
        symbol = str(row["symbol"])
        symbol_lower = symbol.casefold()
        if any(
            symbol_lower == term or symbol_lower.startswith(term) for term in lowered
        ):
            out.append(
                {
                    "fromPath": row["from_path"],
                    "toPath": row["to_path"],
                    "line": int(row["line"]),
                    "refKind": row["ref_kind"],
                    "symbol": symbol,
                }
            )
    return out


def _touch_meta(conn: sqlite3.Connection, key: str) -> None:
    """写一条 meta 时间戳。"""
    from myagentflow.knowledge.owned.ids import utc_now

    conn.execute(
        "INSERT OR REPLACE INTO meta(key, value) VALUES (?, ?)", (key, utc_now())
    )
