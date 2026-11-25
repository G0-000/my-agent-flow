"""一、文件说明
    用户事项业务层：CRUD + 过滤分页。JSON 存储不提供查询能力，
    所以过滤/排序都在这里做；数据量大时应换成 DB，而不是把逻辑塞进 store。

二、目录结构
    packages/harness/myagentflow/items/
    ├── models.py
    ├── store.py
    └── service.py ← 本文件

三、关键方法
    list_items()   过滤 status/priority/tag/q，按 updated_at 倒序分页。
    get_item()     按 id 取事项；缺失时抛 NotFoundError。
    create_item()  title 必填，status/priority 白名单校验。
    update_item()  只允许白名单字段，未知字段忽略。
    delete_item()  物理删除，未命中抛 NotFoundError。
"""

from __future__ import annotations

import uuid
from typing import Any

from myagentflow.admin.errors import NotFoundError, ValidationError
from myagentflow.items import store as item_store
from myagentflow.items.models import (
    ITEM_PRIORITIES,
    ITEM_STATUSES,
    ItemPriority,
    ItemStatus,
    UserItem,
)
from myagentflow.timeutil import beijing_now_iso

_UPDATABLE = frozenset(
    {
        "title",
        "notes",
        "conclusion",
        "status",
        "priority",
        "due_at",
        "tags",
        "assignee_intent",
        "assignee_label",
        "progress",
        "source",
        "source_ref",
        "org_id",
        "owner_scope_id",
    }
)


def _now() -> str:
    return beijing_now_iso()


def _new_id() -> str:
    return f"item_{uuid.uuid4().hex[:12]}"


def _normalize_tags(raw: Any) -> list[str]:
    """字符串按中英文逗号切；列表去重；最多 20 个。"""
    if raw is None:
        return []
    if isinstance(raw, str):
        parts = [p.strip() for p in raw.replace("，", ",").split(",")]
        return [p for p in parts if p][:20]
    if isinstance(raw, list):
        out: list[str] = []
        for x in raw:
            s = str(x or "").strip()
            if s and s not in out:
                out.append(s)
            if len(out) >= 20:
                break
        return out
    return []


def _parse_item(row: dict[str, Any]) -> UserItem:
    try:
        return UserItem.model_validate(row)
    except Exception as exc:
        raise ValidationError(f"invalid item row: {exc}") from exc


def list_items(
    *,
    status: str | None = None,
    priority: str | None = None,
    tag: str | None = None,
    q: str | None = None,
    include_done: bool = True,
    page: int = 1,
    page_size: int = 20,
    is_admin: bool = False,
    personal_scope: str | None = None,
    org_scope: str | None = None,
    principal: Any = None,
    filter_visibility: bool = False,
) -> dict[str, Any]:
    """可见性参数保留签名但本章未实现（没有 principal 体系），不做假过滤。"""
    del is_admin, personal_scope, org_scope, principal, filter_visibility
    status_f = str(status or "").strip().lower() or None
    priority_f = str(priority or "").strip().lower() or None
    tag_f = str(tag or "").strip() or None
    query = str(q or "").strip().lower()
    try:
        page_n = max(1, int(page or 1))
    except (TypeError, ValueError):
        page_n = 1
    try:
        size_n = max(1, min(200, int(page_size or 20)))
    except (TypeError, ValueError):
        size_n = 20

    rows: list[dict[str, Any]] = []
    for raw in item_store.list_raw_items():
        if not isinstance(raw, dict):
            continue
        try:
            item = _parse_item(raw)
        except ValidationError:
            continue
        if status_f and str(item.status) != status_f:
            continue
        if priority_f and str(item.priority) != priority_f:
            continue
        if not include_done and item.status == ItemStatus.DONE:
            continue
        if tag_f and tag_f not in (item.tags or []):
            continue
        if query:
            blob = f"{item.title} {item.notes} {item.conclusion} {' '.join(item.tags or [])}".lower()
            if query not in blob:
                continue
        rows.append(item.to_public_dict())
    rows.sort(
        key=lambda r: (r.get("updated_at") or "", r.get("created_at") or ""),
        reverse=True,
    )
    total = len(rows)
    pages = max(1, (total + size_n - 1) // size_n) if total else 1
    page_n = min(page_n, pages)
    start = (page_n - 1) * size_n
    return {
        "ok": True,
        "items": rows[start : start + size_n],
        "total": total,
        "page": page_n,
        "page_size": size_n,
        "pages": pages,
    }


def get_item(item_id: str) -> dict[str, Any]:
    iid = str(item_id or "").strip()
    if not iid:
        raise ValidationError("item_id is required")
    for raw in item_store.list_raw_items():
        if isinstance(raw, dict) and str(raw.get("id") or "") == iid:
            return {"ok": True, "item": _parse_item(raw).to_public_dict()}
    raise NotFoundError(f"item '{iid}' not found")


def create_item(
    *,
    title: str,
    notes: str = "",
    conclusion: str = "",
    status: str | None = None,
    priority: str | None = None,
    due_at: str | None = None,
    tags: Any = None,
    assignee_intent: str | None = None,
    assignee_label: str | None = None,
    source: str = "user",
    source_ref: str | None = None,
    progress: int | None = None,
    org_id: str | None = None,
    owner_scope_id: str | None = None,
    created_by: str | None = None,
) -> dict[str, Any]:
    title_n = str(title or "").strip()
    if not title_n:
        raise ValidationError("title is required")
    st = str(status or ItemStatus.TODO).strip().lower()
    if st not in ITEM_STATUSES:
        raise ValidationError(f"invalid status: {st}")
    pri = str(priority or ItemPriority.NORMAL).strip().lower()
    if pri not in ITEM_PRIORITIES:
        raise ValidationError(f"invalid priority: {pri}")
    now = _now()
    item = UserItem(
        id=_new_id(),
        title=title_n,
        notes=str(notes or "").strip(),
        conclusion=str(conclusion or "").strip(),
        status=ItemStatus(st),
        priority=ItemPriority(pri),
        due_at=str(due_at or "").strip() or None,
        tags=_normalize_tags(tags),
        assignee_intent=str(assignee_intent or "").strip() or None,
        assignee_label=str(assignee_label or "").strip() or None,
        linked_task_ids=[],
        progress=max(0, min(100, int(progress if progress is not None else 0))),
        source=str(source or "user").strip() or "user",
        source_ref=str(source_ref or "").strip() or None,
        org_id=str(org_id or "").strip() or None,
        owner_scope_id=str(owner_scope_id or "").strip() or None,
        created_by=str(created_by or "").strip() or None,
        created_at=now,
        updated_at=now,
    )
    saved = item_store.upsert_raw_item(item.model_dump())
    return {"ok": True, "item": _parse_item(saved).to_public_dict()}


def update_item(item_id: str, patch: dict[str, Any] | None) -> dict[str, Any]:
    """白名单字段更新；status/priority 非法直接拒绝，不做静默降级。"""
    iid = str(item_id or "").strip()
    if not iid:
        raise ValidationError("item_id is required")
    patch = patch if isinstance(patch, dict) else {}
    found: dict[str, Any] | None = None
    for raw in item_store.list_raw_items():
        if isinstance(raw, dict) and str(raw.get("id") or "") == iid:
            found = dict(raw)
            break
    if found is None:
        raise NotFoundError(f"item '{iid}' not found")
    item = _parse_item(found)
    data = item.model_dump()
    for key, value in patch.items():
        if key not in _UPDATABLE:
            continue
        if key == "status":
            st = str(value or "").strip().lower()
            if st not in ITEM_STATUSES:
                raise ValidationError(f"invalid status: {st}")
            data["status"] = st
        elif key == "priority":
            pri = str(value or "").strip().lower()
            if pri not in ITEM_PRIORITIES:
                raise ValidationError(f"invalid priority: {pri}")
            data["priority"] = pri
        elif key == "tags":
            data["tags"] = _normalize_tags(value)
        elif key == "progress":
            try:
                data["progress"] = max(0, min(100, int(value)))
            except (TypeError, ValueError) as exc:
                raise ValidationError("progress must be 0..100") from exc
        elif key == "due_at":
            data["due_at"] = str(value or "").strip() or None
        else:
            data[key] = str(value or "").strip()
    data["updated_at"] = _now()
    saved = item_store.upsert_raw_item(data)
    return {"ok": True, "item": _parse_item(saved).to_public_dict()}


def delete_item(item_id: str) -> dict[str, Any]:
    iid = str(item_id or "").strip()
    if not iid:
        raise ValidationError("item_id is required")
    if not item_store.delete_raw_item(iid):
        raise NotFoundError(f"item '{iid}' not found")
    return {"ok": True, "deleted": iid}
