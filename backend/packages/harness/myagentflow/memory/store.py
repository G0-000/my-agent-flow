"""一、文件说明
    记忆原子表：mem_namespaces + mem_atoms，一条记忆就是一个 atom。
    为什么用 atom 而不是一整份 JSON：召回要按条目打分、删除要精确到条，
    JSON 只能整份读写，做不到「只忘掉这一条」。

二、目录结构
    packages/harness/myagentflow/memory/
    ├── __init__.py
    ├── namespaces.py  命名空间 id
    ├── store.py       ← 本文件：原子表读写
    ├── facade.py      remember / recall / forget
    └── recall_snapshot.py

三、关键方法
    ensure_namespace()      建/更新命名空间，返回规范 id。
    upsert_atom()          写一条；subject_key 相同则替换旧值。
    soft_delete_atom()     软删：保留行，置 deleted_at。
    list_namespace_atoms() 按命名空间/layer/pin 列。
    search_keyword_ns()    关键词召回：词命中数 + 重要性排序。
    count_active_atoms()   命名空间活跃条数。
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from myagentflow.config.paths import get_paths
from myagentflow.memory.namespaces import parse_namespace
from myagentflow.timeutil import utc_now_iso_z

_VALID_LAYERS = frozenset({"episodic", "semantic", "procedural"})
_LAYER_ALIASES = {
    "journal": "episodic",
    "semantic_self": "semantic",
    "fact": "semantic",
    "episode": "episodic",
    "howto": "procedural",
}

_LATIN_TOKEN_RE = re.compile(r"[A-Za-z0-9_]{2,}")
_CJK_RUN_RE = re.compile(r"[\u4e00-\u9fff]{2,}")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS mem_namespaces (
    id          TEXT PRIMARY KEY,
    kind        TEXT NOT NULL,
    owner_ref   TEXT NOT NULL,
    title       TEXT NOT NULL DEFAULT '',
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS mem_atoms (
    id            TEXT PRIMARY KEY,
    namespace_id  TEXT NOT NULL,
    layer         TEXT NOT NULL,
    kind          TEXT NOT NULL,
    content       TEXT NOT NULL,
    summary       TEXT NOT NULL DEFAULT '',
    importance    REAL NOT NULL DEFAULT 0.5,
    confidence    REAL NOT NULL DEFAULT 0.7,
    vitality      REAL NOT NULL DEFAULT 1.0,
    subject_key   TEXT NOT NULL DEFAULT '',
    evidence_json TEXT NOT NULL DEFAULT '{}',
    tags_json     TEXT NOT NULL DEFAULT '[]',
    source        TEXT NOT NULL DEFAULT '',
    source_path   TEXT NOT NULL DEFAULT '',
    revision      INTEGER NOT NULL DEFAULT 1,
    pin           INTEGER NOT NULL DEFAULT 0,
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL,
    last_accessed_at TEXT,
    deleted_at    TEXT
);
CREATE INDEX IF NOT EXISTS idx_mem_atoms_ns ON mem_atoms(namespace_id, deleted_at, updated_at);
"""


def _db_path() -> Path:
    """可测试的库路径：$MYAF_MEMORY_DB 优先，否则 {base_dir}/memory.sqlite。"""
    raw = os.environ.get("MYAF_MEMORY_DB", "").strip()
    if raw:
        p = Path(raw)
    else:
        p = get_paths().base_dir / "memory.sqlite"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


@contextmanager
def _db() -> Iterator[sqlite3.Connection]:
    """每次操作开一条连接；短事务，避免长连接在测试/多线程里串状态。"""
    conn = sqlite3.connect(str(_db_path()), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        conn.executescript(_SCHEMA)
        yield conn
        conn.commit()
    finally:
        conn.close()


def _dumps(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


def _loads_obj(raw: str | None, default: Any) -> Any:
    if not raw:
        return default
    try:
        return json.loads(raw)
    except Exception:
        return default


def _norm_layer(layer: str) -> str:
    """把 journal/fact/howto 等别名归一到三层层级。"""
    raw = (layer or "semantic").strip().lower()
    mapped = _LAYER_ALIASES.get(raw, raw)
    return mapped if mapped in _VALID_LAYERS else "semantic"


def clamp01(v: float, default: float = 0.5) -> float:
    """夹到 [0,1]；非法值用 default。"""
    try:
        return max(0.0, min(1.0, float(v)))
    except (TypeError, ValueError):
        return default


def _keyword_search_terms(query: str) -> list[str]:
    """拆关键词：拉丁词 + 连续中文段 + 中文二元组。"""
    q = (query or "").strip()
    if not q:
        return []
    terms: list[str] = []
    seen: set[str] = set()

    def _add(t: str) -> None:
        t = t.strip()
        if len(t) < 2 or t in seen:
            return
        seen.add(t)
        terms.append(t)

    safe = q.replace('"', " ").replace("'", " ")
    for tok in safe.split():
        _add(tok)
    for m in _LATIN_TOKEN_RE.finditer(safe):
        _add(m.group(0))
    for m in _CJK_RUN_RE.finditer(safe):
        run = m.group(0)
        _add(run)
        if len(run) >= 2:
            for i in range(len(run) - 1):
                _add(run[i : i + 2])
    if not terms:
        _add(safe)
    terms.sort(key=lambda t: (-len(t), t))
    return terms[:24]


def ensure_namespace(
    ns_id: str,
    *,
    title: str = "",
    org_id: str | None = None,
    owner_scope_id: str | None = None,
    created_by: str | None = None,
) -> str:
    """建/更新命名空间，返回规范 id；后三个参数只为签名兼容，当前不落库。"""
    del org_id, owner_scope_id, created_by
    kind, owner = parse_namespace(ns_id)
    nid = f"{kind}:{owner}" if kind and owner else ns_id
    now = utc_now_iso_z()
    with _db() as conn:
        row = conn.execute(
            "SELECT id FROM mem_namespaces WHERE id=?", (nid,)
        ).fetchone()
        if row:
            conn.execute(
                "UPDATE mem_namespaces SET updated_at=?, title=CASE WHEN ?!='' THEN ? ELSE title END WHERE id=?",
                (now, title, title, nid),
            )
            return nid
        conn.execute(
            "INSERT INTO mem_namespaces(id, kind, owner_ref, title, created_at, updated_at) VALUES (?,?,?,?,?,?)",
            (nid, kind or "user", owner or "default", title or nid, now, now),
        )
    return nid


def _row_to_atom(row: sqlite3.Row) -> dict[str, Any]:
    d = dict(row)
    d["evidence"] = _loads_obj(d.pop("evidence_json", None), {})
    d["tags"] = _loads_obj(d.pop("tags_json", None), [])
    d["pin"] = bool(int(d.get("pin") or 0))
    return d


def upsert_atom(
    *,
    namespace_id: str,
    content: str,
    layer: str = "semantic",
    kind: str = "fact",
    summary: str = "",
    importance: float = 0.5,
    confidence: float = 0.7,
    vitality: float = 1.0,
    subject_key: str = "",
    evidence: dict[str, Any] | None = None,
    tags: list[Any] | None = None,
    source: str = "",
    pin: bool = False,
    atom_id: str | None = None,
    embedding: list[float] | None = None,
    replace_subject: bool = True,
) -> str | None:
    """写一条记忆；subject_key 相同则替换旧值，避免同一事实堆多份。"""
    del embedding  # 向量召回尚未实现；字段保留只为签名兼容
    text = " ".join(str(content or "").strip().split())
    if not text:
        return None
    ns = ensure_namespace(namespace_id)
    now = utc_now_iso_z()
    layer_n = _norm_layer(layer)
    sk = (subject_key or "").strip()
    aid = (atom_id or "").strip() or str(uuid.uuid4())

    with _db() as conn:
        if replace_subject and sk:
            existing = conn.execute(
                """
                SELECT id, revision FROM mem_atoms
                WHERE namespace_id=? AND subject_key=? AND deleted_at IS NULL
                ORDER BY updated_at DESC LIMIT 1
                """,
                (ns, sk),
            ).fetchone()
            if existing:
                aid = existing["id"]
                rev = int(existing["revision"] or 1) + 1
                conn.execute(
                    """
                    UPDATE mem_atoms SET
                      layer=?, kind=?, content=?, summary=?, importance=?, confidence=?,
                      vitality=?, evidence_json=?, tags_json=?, source=?, revision=?,
                      pin=?, updated_at=?
                    WHERE id=?
                    """,
                    (
                        layer_n,
                        kind or "fact",
                        text,
                        summary or "",
                        clamp01(importance, 0.5),
                        clamp01(confidence, 0.7),
                        clamp01(vitality, 1.0),
                        _dumps(evidence or {}),
                        _dumps(tags or []),
                        source or "",
                        rev,
                        1 if pin else 0,
                        now,
                        aid,
                    ),
                )
                return aid

        conn.execute(
            """
            INSERT INTO mem_atoms(
              id, namespace_id, layer, kind, content, summary, importance, confidence,
              vitality, subject_key, evidence_json, tags_json, source, revision, pin,
              created_at, updated_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                aid,
                ns,
                layer_n,
                kind or "fact",
                text,
                summary or "",
                clamp01(importance, 0.5),
                clamp01(confidence, 0.7),
                clamp01(vitality, 1.0),
                sk,
                _dumps(evidence or {}),
                _dumps(tags or []),
                source or "",
                1,
                1 if pin else 0,
                now,
                now,
            ),
        )
    return aid


def soft_delete_atom(atom_id: str, *, source: str | None = None) -> bool:
    """软删：置 deleted_at，保留行以便审计/回溯。"""
    aid = (atom_id or "").strip()
    if not aid:
        return False
    now = utc_now_iso_z()
    with _db() as conn:
        cur = conn.execute(
            "UPDATE mem_atoms SET deleted_at=?, updated_at=?, source=CASE WHEN ?!='' THEN ? ELSE source END "
            "WHERE id=? AND deleted_at IS NULL",
            (now, now, source or "", source or "", aid),
        )
        return cur.rowcount > 0


def get_atom(atom_id: str) -> dict[str, Any] | None:
    """按 id 取活跃 atom；已删除返回 None。"""
    aid = (atom_id or "").strip()
    if not aid:
        return None
    with _db() as conn:
        row = conn.execute(
            "SELECT * FROM mem_atoms WHERE id=? AND deleted_at IS NULL", (aid,)
        ).fetchone()
        return _row_to_atom(row) if row else None


def list_namespace_atoms(
    namespace_id: str,
    *,
    layers: list[str] | None = None,
    pinned_only: bool = False,
    limit: int = 200,
) -> list[dict[str, Any]]:
    """列命名空间内的活跃 atom；pin 优先，再按重要性/更新时间。"""
    ns = ensure_namespace(namespace_id)
    clauses = ["namespace_id=?", "deleted_at IS NULL"]
    args: list[Any] = [ns]
    if pinned_only:
        clauses.append("pin=1")
    if layers:
        norms = [_norm_layer(x) for x in layers]
        clauses.append(f"layer IN ({','.join('?' * len(norms))})")
        args.extend(norms)
    args.append(max(1, min(int(limit), 2000)))
    sql = f"""
        SELECT * FROM mem_atoms
        WHERE {" AND ".join(clauses)}
        ORDER BY pin DESC, importance DESC, updated_at DESC
        LIMIT ?
    """
    with _db() as conn:
        rows = conn.execute(sql, args).fetchall()
        return [_row_to_atom(r) for r in rows]


def search_keyword_ns(
    namespace_ids: list[str],
    query: str,
    *,
    top_k: int = 20,
    layers: list[str] | None = None,
) -> list[dict[str, Any]]:
    """关键词召回：按命中词长度加权，再按重要性/新鲜度排序。"""
    q = (query or "").strip()
    if not q or not namespace_ids:
        return []
    terms = _keyword_search_terms(q)
    ns_list = [ensure_namespace(n) for n in namespace_ids]
    scored: list[tuple[float, dict[str, Any]]] = []
    for ns in ns_list:
        for atom in list_namespace_atoms(ns, layers=layers, limit=2000):
            text = f"{atom.get('summary') or ''}\n{atom.get('content') or ''}".lower()
            score = 0.0
            for term in terms:
                if term.lower() in text:
                    score += max(1, len(term))
            if score <= 0:
                continue
            score += float(atom.get("importance") or 0) * 2
            if atom.get("pin"):
                score += 5
            scored.append((score, atom))
    scored.sort(key=lambda kv: (kv[0], kv[1].get("updated_at") or ""), reverse=True)
    out: list[dict[str, Any]] = []
    for score, atom in scored[: max(1, int(top_k))]:
        atom = dict(atom)
        atom["score"] = score
        out.append(atom)
    return out


def supersede_atom(
    atom_id: str, keeper_id: str, *, source: str = "consolidate"
) -> bool:
    """把被合并的 atom 软删，并在 source 里留下 keeper id。"""
    return soft_delete_atom(atom_id, source=f"{source}:{keeper_id}")


def touch_accessed(atom_ids: list[str]) -> None:
    """记一次访问；召回排序可据此降低久未使用条目的权重。"""
    ids = [a for a in atom_ids if a]
    if not ids:
        return
    now = utc_now_iso_z()
    with _db() as conn:
        for aid in ids:
            conn.execute(
                "UPDATE mem_atoms SET last_accessed_at=? WHERE id=?", (now, aid)
            )


def set_pin(atom_id: str, pin: bool) -> bool:
    """给一条记忆加/去 pin；pin 的条目不会被归档过滤掉。"""
    aid = (atom_id or "").strip()
    if not aid:
        return False
    now = utc_now_iso_z()
    with _db() as conn:
        cur = conn.execute(
            "UPDATE mem_atoms SET pin=?, updated_at=? WHERE id=? AND deleted_at IS NULL",
            (1 if pin else 0, now, aid),
        )
        return cur.rowcount > 0


def count_active_atoms(namespace_id: str) -> int:
    """命名空间内活跃 atom 数；用于触发巩固阈值。"""
    ns = ensure_namespace(namespace_id)
    with _db() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS c FROM mem_atoms WHERE namespace_id=? AND deleted_at IS NULL",
            (ns,),
        ).fetchone()
        return int(row["c"] if row else 0)


def update_atom_fields(
    atom_id: str,
    *,
    content: str | None = None,
    summary: str | None = None,
    importance: float | None = None,
    confidence: float | None = None,
    vitality: float | None = None,
    source: str | None = None,
    source_path: str | None = None,
) -> bool:
    """局部更新 atom；只改传入的字段。"""
    aid = (atom_id or "").strip()
    if not aid:
        return False
    now = utc_now_iso_z()
    sets: list[str] = ["updated_at=?"]
    args: list[Any] = [now]
    if content is not None:
        sets.append("content=?")
        args.append(" ".join(str(content).strip().split()))
    if summary is not None:
        sets.append("summary=?")
        args.append(summary)
    if importance is not None:
        sets.append("importance=?")
        args.append(clamp01(importance, 0.5))
    if confidence is not None:
        sets.append("confidence=?")
        args.append(clamp01(confidence, 0.7))
    if vitality is not None:
        sets.append("vitality=?")
        args.append(clamp01(vitality, 1.0))
    if source is not None:
        sets.append("source=?")
        args.append(source)
    if source_path is not None:
        sets.append("source_path=?")
        args.append(str(source_path or ""))
    args.append(aid)
    with _db() as conn:
        cur = conn.execute(
            f"UPDATE mem_atoms SET {', '.join(sets)} WHERE id=? AND deleted_at IS NULL",
            args,
        )
        return cur.rowcount > 0
