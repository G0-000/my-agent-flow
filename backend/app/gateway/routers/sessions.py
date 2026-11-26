"""会话与消息的只读接口：前端拿会话列表、翻历史消息。

为什么单独一个路由：聊天接口负责「写」和「流」，读历史是另一条路径；
把它放进来会让 `/api/chat` 既管生成又管分页，职责过重。

分页用 `before_seq` 游标，而不是 offset：
消息只追加不修改，seq 天然稳定；offset 在并发追加时会重复或漏行。
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

router = APIRouter()


@router.get("/sessions")
def list_sessions(limit: int = Query(default=50, ge=1, le=200)) -> dict:
    from myagentflow.persistence.session_repositories import list_sessions_for_ui

    rows = list_sessions_for_ui(limit=limit)
    return {"sessions": rows, "count": len(rows)}


@router.get("/sessions/{thread_id}/messages")
def list_session_messages(
    thread_id: str,
    limit: int = Query(default=50, ge=1, le=200),
    before_seq: int | None = Query(default=None, ge=1),
) -> dict:
    from myagentflow.persistence.chat_message_repositories import list_messages
    from myagentflow.persistence.session_repositories import get_session_row_for_ui

    session = get_session_row_for_ui(thread_id)
    if session is None:
        raise HTTPException(status_code=404, detail=f"session {thread_id} 不存在")
    rows = list_messages(thread_id, limit=limit, before_seq=before_seq)
    next_before = rows[0]["seq"] if len(rows) == limit else None
    return {
        "thread_id": thread_id,
        "messages": rows,
        "count": len(rows),
        "next_before_seq": next_before,
    }


@router.get("/sessions/{thread_id}/artifacts")
def list_session_artifacts(thread_id: str) -> dict:
    """本轮/历史工具产出的文件与链接；来自检查点状态，不靠正则扫聊天正文。"""
    from myagentflow.agents.checkpointer import get_checkpointer
    from myagentflow.agents.checkpointer.thread_state_reader import read_thread_state

    state = read_thread_state(get_checkpointer(), thread_id)
    values = (state or {}).get("values") or {}
    artifacts = values.get("artifacts") or {}
    items = list(artifacts.values()) if isinstance(artifacts, dict) else []
    return {"thread_id": thread_id, "artifacts": items, "count": len(items)}
