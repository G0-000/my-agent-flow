"""一、文件说明
    Owned Knowledge 表结构：知识库、文档、目录、块、实体节点与边。
    表名与上游同类表保持一致（kb_* / kg_*），字段只保留本章闭环用得到的列。

二、目录结构
    packages/harness/myagentflow/knowledge/owned/
    ├── __init__.py
    ├── db.py  连接与锁
    ├── ids.py  id 与时间
    ├── schema.py  ← 本文件：表结构
    ├── service.py  知识库、文档、目录与块
    └── kg.py  实体图节点与边

三、关键方法
    ensure_schema()  幂等建表并写 schema 版本。
"""

from __future__ import annotations

import sqlite3

SCHEMA_VERSION = "ch05_owned_v1"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS kb_schema_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS kb_bases (
    kb_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    owner_scope TEXT NOT NULL DEFAULT 'public',
    description TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS kb_documents (
    doc_id TEXT PRIMARY KEY,
    kb_id TEXT NOT NULL,
    title TEXT NOT NULL,
    file_name TEXT NOT NULL,
    content TEXT NOT NULL,
    folder_path TEXT NOT NULL DEFAULT '',
    source_type TEXT NOT NULL DEFAULT 'manual',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_kb_documents_kb ON kb_documents(kb_id);

CREATE TABLE IF NOT EXISTS kb_folders (
    folder_id TEXT PRIMARY KEY,
    kb_id TEXT NOT NULL,
    path TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_kb_folders_path ON kb_folders(kb_id, path);

CREATE TABLE IF NOT EXISTS kb_chunks (
    chunk_id TEXT PRIMARY KEY,
    kb_id TEXT NOT NULL,
    doc_id TEXT NOT NULL,
    ordinal INTEGER NOT NULL,
    content TEXT NOT NULL,
    heading_path TEXT NOT NULL DEFAULT '',
    token_estimate INTEGER NOT NULL DEFAULT 0,
    char_start INTEGER NOT NULL DEFAULT 0,
    char_end INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_kb_chunks_doc ON kb_chunks(doc_id, ordinal);

CREATE TABLE IF NOT EXISTS kg_nodes (
    id TEXT PRIMARY KEY,
    kb_id TEXT NOT NULL,
    name TEXT NOT NULL,
    attrs_json TEXT NOT NULL DEFAULT '[]',
    chunk_ids_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_kg_nodes_kb_name ON kg_nodes(kb_id, name);

CREATE TABLE IF NOT EXISTS kg_edges (
    id TEXT PRIMARY KEY,
    kb_id TEXT NOT NULL,
    src_node_id TEXT NOT NULL,
    dst_node_id TEXT NOT NULL,
    rel_type TEXT NOT NULL DEFAULT 'related_to',
    created_at TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_kg_edges_unique
    ON kg_edges(kb_id, src_node_id, dst_node_id, rel_type);
"""


def ensure_schema(conn: sqlite3.Connection) -> None:
    """建表并记录版本；重复调用不会清数据。"""
    conn.executescript(_SCHEMA)
    conn.execute(
        "INSERT OR REPLACE INTO kb_schema_meta(key, value) VALUES ('schema_version', ?)",
        (SCHEMA_VERSION,),
    )
    conn.commit()
