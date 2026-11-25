"""一、文件说明
    Owned Knowledge 业务入口：知识库、归属范围、文档、目录与块的读写。
    本章把「建库 → 上传 Markdown → 切块 → 列目录/文档」做成闭环；解析二进制、
    异步索引队列与向量写入由后续章节接入，不在本文件里假装完成。

二、目录结构
    packages/harness/myagentflow/knowledge/owned/
    ├── __init__.py
    ├── db.py  连接与锁
    ├── ids.py  id 与时间
    ├── schema.py  表结构
    ├── service.py  ← 本文件：知识库、文档、目录与块
    └── kg.py  实体图节点与边

三、关键方法
    create_base()            建库；owner_scope 决定谁能检索到。
    list_bases()             按归属范围过滤，public 对所有 scope 可见。
    upload_manual_markdown() 写入 Markdown 文档并按标题切块。
    list_folders()           从显式目录与文档路径还原知识地图的目录层。
"""

from __future__ import annotations

from typing import Any

from myagentflow.knowledge.index_builder import enrich_chunk_indexes
from myagentflow.knowledge.owned.db import db
from myagentflow.knowledge.owned.ids import new_id, utc_now
from myagentflow.knowledge.wiki_chunker import auto_chunk_document

_SKIP_FOLDER_NAMES = {".git", ".svn", "__pycache__", "node_modules", ".venv"}


def list_bases(owner_scope: str | None = None) -> list[dict[str, Any]]:
    """列出知识库；传 owner_scope 时只返回 public + 同 scope 的库。"""
    with db() as conn:
        if owner_scope:
            rows = conn.execute(
                "SELECT * FROM kb_bases WHERE owner_scope IN ('public', ?) ORDER BY created_at DESC",
                (owner_scope,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM kb_bases ORDER BY created_at DESC"
            ).fetchall()
    return [_row_base(row) for row in rows]


def create_base(payload: dict[str, Any]) -> dict[str, Any]:
    """按 payload 建库；name 必填，ownerScope 默认 public。"""
    name = str(payload.get("name") or payload.get("title") or "").strip()
    if not name:
        raise ValueError("base name is required")
    kb_id = str(payload.get("kbId") or payload.get("kb_id") or "").strip() or new_id(
        "kb_"
    )
    owner_scope = str(
        payload.get("ownerScope") or payload.get("owner_scope") or "public"
    ).strip()
    description = str(payload.get("description") or "").strip()
    now = utc_now()
    with db() as conn:
        conn.execute(
            """
            INSERT INTO kb_bases(kb_id, name, owner_scope, description, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (kb_id, name, owner_scope, description, now, now),
        )
    return get_base(kb_id) or {}


def get_base(kb_id: str) -> dict[str, Any] | None:
    """按 kb_id 取知识库；不存在返回 None。"""
    with db() as conn:
        row = conn.execute(
            "SELECT * FROM kb_bases WHERE kb_id = ?", (kb_id,)
        ).fetchone()
    return _row_base(row) if row else None


def set_kb_owner_scope(kb_id: str, owner_scope: str) -> dict[str, Any]:
    """改知识库归属范围；用于把 public 库收归到某个工作区。"""
    scope = str(owner_scope or "").strip()
    if not scope:
        raise ValueError("owner_scope is required")
    with db() as conn:
        conn.execute(
            "UPDATE kb_bases SET owner_scope = ?, updated_at = ? WHERE kb_id = ?",
            (scope, utc_now(), kb_id),
        )
    return get_base(kb_id) or {}


def kb_visible_to_principal(kb_id: str, owner_scope: str | None) -> bool:
    """判断当前 scope 是否能看到该库；不存在的库一律不可见。"""
    base = get_base(kb_id)
    if not base:
        return False
    if base["ownerScope"] == "public":
        return True
    return bool(owner_scope and base["ownerScope"] == owner_scope)


def delete_base(kb_id: str) -> None:
    """删除知识库及其文档、块、目录与实体图；不触碰其他库。"""
    with db() as conn:
        conn.execute("DELETE FROM kb_chunks WHERE kb_id = ?", (kb_id,))
        conn.execute("DELETE FROM kb_documents WHERE kb_id = ?", (kb_id,))
        conn.execute("DELETE FROM kb_folders WHERE kb_id = ?", (kb_id,))
        conn.execute("DELETE FROM kg_edges WHERE kb_id = ?", (kb_id,))
        conn.execute("DELETE FROM kg_nodes WHERE kb_id = ?", (kb_id,))
        conn.execute("DELETE FROM kb_bases WHERE kb_id = ?", (kb_id,))


def list_documents(kb_id: str) -> list[dict[str, Any]]:
    """列出某库文档；附带 chunk 数，便于判断是否已经切块。"""
    with db() as conn:
        rows = conn.execute(
            """
            SELECT d.*, COUNT(c.chunk_id) AS chunk_count
            FROM kb_documents d
            LEFT JOIN kb_chunks c ON c.doc_id = d.doc_id
            WHERE d.kb_id = ?
            GROUP BY d.doc_id
            ORDER BY d.created_at DESC
            """,
            (kb_id,),
        ).fetchall()
    return [_row_doc(row) for row in rows]


def get_document(doc_id: str) -> dict[str, Any] | None:
    """按 doc_id 取文档正文与元数据。"""
    with db() as conn:
        row = conn.execute(
            """
            SELECT d.*, COUNT(c.chunk_id) AS chunk_count
            FROM kb_documents d
            LEFT JOIN kb_chunks c ON c.doc_id = d.doc_id
            WHERE d.doc_id = ?
            GROUP BY d.doc_id
            """,
            (doc_id,),
        ).fetchone()
    return _row_doc(row) if row else None


def upload_manual_markdown(
    kb_id: str,
    *,
    title: str,
    content: str,
    folder_path: str = "",
) -> dict[str, Any]:
    """写入一篇 Markdown 文档，按标题切块后落库。"""
    if not get_base(kb_id):
        raise ValueError("knowledge base not found")
    text = str(content or "")
    if not text.strip():
        raise ValueError("content is required")
    label = str(title or "").strip() or "note"
    file_name = f"{label}.md"
    folder = _resolve_folder_path(folder_path)
    now = utc_now()
    doc_id = new_id("doc_")

    with db() as conn:
        _ensure_folder_rows(conn, kb_id, folder, now=now)
        conn.execute(
            """
            INSERT INTO kb_documents(
                doc_id, kb_id, title, file_name, content, folder_path, source_type, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, 'manual', ?, ?)
            """,
            (doc_id, kb_id, label, file_name, text, folder, now, now),
        )

        chunks = enrich_chunk_indexes(
            auto_chunk_document(text, file_name=file_name), file_name=file_name
        )
        rows: list[tuple[Any, ...]] = []
        for ordinal, chunk in enumerate(chunks):
            rows.append(
                (
                    new_id("chunk_"),
                    kb_id,
                    doc_id,
                    ordinal,
                    chunk["content"],
                    chunk.get("heading_path") or "",
                    int(chunk.get("token_count") or 0),
                    int(chunk.get("char_start") or 0),
                    int(chunk.get("char_end") or 0),
                    now,
                )
            )
        if rows:
            conn.executemany(
                """
                INSERT INTO kb_chunks(
                    chunk_id, kb_id, doc_id, ordinal, content, heading_path,
                    token_estimate, char_start, char_end, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                rows,
            )
    return get_document(doc_id) or {}


def list_chunks(doc_id: str) -> list[dict[str, Any]]:
    """列出某文档的全部块，按 ordinal 升序。"""
    with db() as conn:
        rows = conn.execute(
            """
            SELECT * FROM kb_chunks WHERE doc_id = ? ORDER BY ordinal ASC
            """,
            (doc_id,),
        ).fetchall()
    return [
        {
            "id": row["chunk_id"],
            "ordinal": row["ordinal"],
            "content": row["content"],
            "headingPath": row["heading_path"],
            "tokenEstimate": row["token_estimate"],
            "charStart": row["char_start"],
            "charEnd": row["char_end"],
        }
        for row in rows
    ]


def list_folders(kb_id: str) -> list[dict[str, Any]]:
    """返回目录地图：显式目录 + 文档路径推导出的隐式父目录。"""
    with db() as conn:
        explicit_rows = conn.execute(
            "SELECT path, created_at FROM kb_folders WHERE kb_id = ?", (kb_id,)
        ).fetchall()
        doc_rows = conn.execute(
            "SELECT folder_path FROM kb_documents WHERE kb_id = ?", (kb_id,)
        ).fetchall()

    explicit = {
        _resolve_folder_path(row["path"]): row["created_at"]
        for row in explicit_rows
        if row["path"]
    }
    paths: set[str] = set(explicit)
    for row in doc_rows:
        raw = _resolve_folder_path(row["folder_path"])
        if not raw:
            continue
        parts = raw.split("/")
        for index in range(1, len(parts) + 1):
            paths.add("/".join(parts[:index]))

    out: list[dict[str, Any]] = []
    for path in sorted(paths):
        out.append(
            {
                "path": path,
                "name": path.split("/")[-1],
                "explicit": path in explicit,
                "createdAt": explicit.get(path, ""),
            }
        )
    return out


def create_folder(kb_id: str, path: str) -> dict[str, Any]:
    """显式创建一个目录（含所有父目录）；重复创建返回既有的路径。"""
    if not get_base(kb_id):
        raise ValueError("knowledge base not found")
    folder = _resolve_folder_path(path)
    if not folder:
        raise ValueError("folder path required")
    now = utc_now()
    with db() as conn:
        _ensure_folder_rows(conn, kb_id, folder, now=now)
    return {"path": folder, "name": folder.split("/")[-1], "explicit": True}


def _resolve_folder_path(path: str | None) -> str:
    """归一化目录路径：斜杠分隔、去掉空段与危险段，拒绝隐藏目录。"""
    raw = str(path or "").strip().replace("\\", "/")
    parts = [part.strip() for part in raw.split("/") if part.strip()]
    if any(part in {".", ".."} or part.startswith(".") for part in parts):
        raise ValueError(f"hidden or unsafe folder path: {path}")
    if any(part in _SKIP_FOLDER_NAMES for part in parts):
        raise ValueError(f"skipped folder path: {path}")
    return "/".join(parts)


def _ensure_folder_rows(conn: Any, kb_id: str, path: str, *, now: str) -> None:
    """把 ``a/b/c`` 的每一层都写成显式目录行，父目录先于子目录。"""
    if not path:
        return
    parts = path.split("/")
    for index in range(1, len(parts) + 1):
        current = "/".join(parts[:index])
        conn.execute(
            """
            INSERT OR IGNORE INTO kb_folders(folder_id, kb_id, path, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (new_id("fld_"), kb_id, current, now, now),
        )


def _row_base(row: Any) -> dict[str, Any]:
    """把 kb_bases 行转成 API 使用的 camelCase 字段。"""
    return {
        "kbId": row["kb_id"],
        "name": row["name"],
        "ownerScope": row["owner_scope"],
        "description": row["description"],
        "createdAt": row["created_at"],
        "updatedAt": row["updated_at"],
    }


def _row_doc(row: Any) -> dict[str, Any]:
    """把 kb_documents 行转成 API 使用的 camelCase 字段。"""
    return {
        "id": row["doc_id"],
        "kbId": row["kb_id"],
        "title": row["title"],
        "fileName": row["file_name"],
        "folderPath": row["folder_path"],
        "sourceType": row["source_type"],
        "content": row["content"],
        "chunkCount": int(row["chunk_count"]),
        "createdAt": row["created_at"],
        "updatedAt": row["updated_at"],
    }
