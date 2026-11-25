"""一、文件说明
    Owned Knowledge 的实体图：节点是实体/主题，边是关系；落在 SQLite，不引 Neo4j。
    为什么用图补知识地图：目录树只回答「文档在哪」，实体图回答「这几个概念怎么连」。

二、目录结构
    packages/harness/myagentflow/knowledge/owned/
    ├── __init__.py
    ├── db.py  连接与锁
    ├── ids.py  id 与时间
    ├── schema.py  表结构
    ├── service.py  知识库、文档、目录与块
    └── kg.py  ← 本文件：实体图节点与边

三、关键方法
    add_triples()       批量写入 (src, rel, dst)，节点自动去重。
    find_nodes_by_query() 按名称模糊查实体，返回关联 chunk id。
    graph_payload()     输出可直接渲染的 nodes/edges。
"""

from __future__ import annotations

import json
import re
from typing import Any

from myagentflow.knowledge.owned.db import db
from myagentflow.knowledge.owned.ids import new_id, utc_now


def upsert_node(
    kb_id: str,
    name: str,
    *,
    chunk_id: str | None = None,
    attrs: list[Any] | None = None,
) -> dict[str, Any]:
    """写入或更新实体节点；同名节点合并 chunk_ids 与 attrs。"""
    label = _norm_name(name)
    if not label:
        raise ValueError("entity name required")
    now = utc_now()
    with db() as conn:
        row = conn.execute(
            "SELECT * FROM kg_nodes WHERE kb_id = ? AND name = ?", (kb_id, label)
        ).fetchone()
        if row:
            node_id = row["id"]
            chunk_ids = _loads(row["chunk_ids_json"], [])
            if chunk_id and chunk_id not in chunk_ids:
                chunk_ids.append(chunk_id)
            attrs_list = _loads(row["attrs_json"], [])
            for attr in attrs or []:
                if attr not in attrs_list:
                    attrs_list.append(attr)
            conn.execute(
                """
                UPDATE kg_nodes
                SET chunk_ids_json = ?, attrs_json = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    json.dumps(chunk_ids, ensure_ascii=False),
                    json.dumps(attrs_list, ensure_ascii=False),
                    now,
                    node_id,
                ),
            )
        else:
            node_id = new_id("kgn_")
            conn.execute(
                """
                INSERT INTO kg_nodes(id, kb_id, name, attrs_json, chunk_ids_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    node_id,
                    kb_id,
                    label,
                    json.dumps(attrs or [], ensure_ascii=False),
                    json.dumps([chunk_id] if chunk_id else [], ensure_ascii=False),
                    now,
                    now,
                ),
            )
        row = conn.execute("SELECT * FROM kg_nodes WHERE id = ?", (node_id,)).fetchone()
    return {
        "id": row["id"],
        "kbId": row["kb_id"],
        "name": row["name"],
        "attrs": _loads(row["attrs_json"], []),
        "chunkIds": _loads(row["chunk_ids_json"], []),
    }


def upsert_edge(kb_id: str, src_id: str, dst_id: str, rel_type: str) -> dict[str, Any]:
    """写入一条有向边；同 src/dst/rel 只保留一条，自环直接拒绝。"""
    rel = _norm_name(rel_type) or "related_to"
    if src_id == dst_id:
        raise ValueError("self-edge not allowed")
    now = utc_now()
    with db() as conn:
        existing = conn.execute(
            """
            SELECT * FROM kg_edges
            WHERE kb_id = ? AND src_node_id = ? AND dst_node_id = ? AND rel_type = ?
            """,
            (kb_id, src_id, dst_id, rel),
        ).fetchone()
        if existing:
            edge_id = existing["id"]
        else:
            edge_id = new_id("kge_")
            conn.execute(
                """
                INSERT INTO kg_edges(id, kb_id, src_node_id, dst_node_id, rel_type, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (edge_id, kb_id, src_id, dst_id, rel, now),
            )
    return {
        "id": edge_id,
        "kbId": kb_id,
        "srcNodeId": src_id,
        "dstNodeId": dst_id,
        "relType": rel,
    }


def add_triples(
    kb_id: str,
    triples: list[tuple[str, str, str]],
    *,
    chunk_id: str | None = None,
) -> dict[str, int]:
    """批量写 ``(src, rel, dst)``，返回节点触碰次数与边新增次数。"""
    nodes = 0
    edges = 0
    for src, rel, dst in triples:
        src_name = _norm_name(src)
        dst_name = _norm_name(dst)
        if not src_name or not dst_name or src_name == dst_name:
            continue
        source = upsert_node(kb_id, src_name, chunk_id=chunk_id)
        target = upsert_node(kb_id, dst_name, chunk_id=chunk_id)
        nodes += 2
        upsert_edge(kb_id, source["id"], target["id"], rel)
        edges += 1
    return {"nodesTouched": nodes, "edgesAdded": edges}


def find_nodes_by_query(
    kb_id: str, query: str, *, limit: int = 8
) -> list[dict[str, Any]]:
    """按名称子串查实体；空查询返回空列表。"""
    label = _norm_name(query)
    if not label:
        return []
    with db() as conn:
        rows = conn.execute(
            """
            SELECT * FROM kg_nodes
            WHERE kb_id = ? AND name LIKE ?
            ORDER BY updated_at DESC
            LIMIT ?
            """,
            (kb_id, f"%{label}%", max(1, int(limit))),
        ).fetchall()
    return [
        {
            "id": row["id"],
            "kbId": row["kb_id"],
            "name": row["name"],
            "attrs": _loads(row["attrs_json"], []),
            "chunkIds": _loads(row["chunk_ids_json"], []),
        }
        for row in rows
    ]


def list_nodes(kb_id: str, *, limit: int = 200) -> list[dict[str, Any]]:
    """列出实体节点，按更新时间倒序。"""
    with db() as conn:
        rows = conn.execute(
            "SELECT * FROM kg_nodes WHERE kb_id = ? ORDER BY updated_at DESC LIMIT ?",
            (kb_id, max(1, int(limit))),
        ).fetchall()
    return [
        {
            "id": row["id"],
            "kbId": row["kb_id"],
            "name": row["name"],
            "attrs": _loads(row["attrs_json"], []),
            "chunkIds": _loads(row["chunk_ids_json"], []),
        }
        for row in rows
    ]


def graph_payload(
    kb_id: str, *, center: str | None = None, limit: int = 80
) -> dict[str, Any]:
    """输出力导向图需要的 nodes/edges；center 存在时只保留一跳邻居。"""
    nodes_raw = list_nodes(kb_id, limit=limit)
    by_id = {node["id"]: node for node in nodes_raw}
    if center and nodes_raw:
        center_node = next(
            (
                node
                for node in nodes_raw
                if node["name"] == center or node["id"] == center
            ),
            None,
        )
        if center_node:
            keep = {center_node["id"]}
            with db() as conn:
                rows = conn.execute(
                    """
                    SELECT src_node_id, dst_node_id FROM kg_edges
                    WHERE kb_id = ? AND (src_node_id = ? OR dst_node_id = ?)
                    """,
                    (kb_id, center_node["id"], center_node["id"]),
                ).fetchall()
            for row in rows:
                keep.add(row["src_node_id"])
                keep.add(row["dst_node_id"])
            nodes_raw = [by_id[node_id] for node_id in keep if node_id in by_id]

    node_ids = {node["id"] for node in nodes_raw}
    with db() as conn:
        if node_ids:
            placeholders = ",".join("?" * len(node_ids))
            edge_rows = conn.execute(
                f"""
                SELECT * FROM kg_edges
                WHERE kb_id = ? AND src_node_id IN ({placeholders}) AND dst_node_id IN ({placeholders})
                LIMIT ?
                """,
                [kb_id, *node_ids, *node_ids, max(1, int(limit)) * 3],
            ).fetchall()
        else:
            edge_rows = []

    nodes = [
        {
            "id": node["id"],
            "label": node["name"],
            "path": node["name"],
            "category": "entity",
        }
        for node in nodes_raw
    ]
    edges = [
        {
            "source": row["src_node_id"],
            "target": row["dst_node_id"],
            "type": row["rel_type"],
            "label": row["rel_type"],
        }
        for row in edge_rows
    ]
    return {
        "kbId": kb_id,
        "kind": "entity",
        "center": center,
        "nodes": nodes,
        "edges": edges,
        "nodeCount": len(nodes),
        "edgeCount": len(edges),
    }


def delete_by_kb(kb_id: str) -> None:
    """删除该库全部实体图数据。"""
    with db() as conn:
        conn.execute("DELETE FROM kg_edges WHERE kb_id = ?", (kb_id,))
        conn.execute("DELETE FROM kg_nodes WHERE kb_id = ?", (kb_id,))


def stats(kb_id: str) -> dict[str, int]:
    """返回节点数与边数。"""
    with db() as conn:
        node_count = conn.execute(
            "SELECT COUNT(*) AS c FROM kg_nodes WHERE kb_id = ?", (kb_id,)
        ).fetchone()["c"]
        edge_count = conn.execute(
            "SELECT COUNT(*) AS c FROM kg_edges WHERE kb_id = ?", (kb_id,)
        ).fetchone()["c"]
    return {"nodeCount": int(node_count), "edgeCount": int(edge_count)}


def _loads(raw: str | None, default: Any) -> Any:
    """安全解析 JSON 列；坏数据退回 default。"""
    try:
        return json.loads(raw or "") if raw else default
    except Exception:
        return default


def _norm_name(name: str) -> str:
    """实体名归一：压缩空白并截断到 120 字符。"""
    return re.sub(r"\s+", " ", str(name or "").strip())[:120]
