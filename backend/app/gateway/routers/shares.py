"""分享接口：创建只读链接、查看快照、导出、吊销。

为什么创建时冻结消息：分享是「那一刻的对话」；之后继续聊的内容不应自动外泄。
吊销按 token 与会话两种粒度，泄露时能一次收回。
"""
from __future__ import annotations

import os
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, Response
from pydantic import BaseModel

router = APIRouter()

_store = None


def get_share_store():
    """进程内单例；路径跟其它运行数据一样放 $MYAF_DATA_DIR。"""
    global _store
    if _store is None:
        from myagentflow.collab.shares import ShareStore

        base = Path(os.environ.get("MYAF_DATA_DIR") or (Path.home() / ".myagentflow"))
        _store = ShareStore(base / "shares.sqlite")
    return _store


def reset_share_store() -> None:
    """测试用：换数据目录后必须丢掉旧连接。"""
    global _store
    _store = None


class ShareIn(BaseModel):
    thread_id: str
    ttl_seconds: int = 7 * 86400


def _load_messages(thread_id: str) -> list[dict]:
    from myagentflow.persistence.chat_message_repositories import list_messages

    return list_messages(thread_id)


def _resolve_or_raise(token: str):
    result = get_share_store().resolve(token)
    if result.status == "missing":
        raise HTTPException(status_code=404, detail="分享不存在")
    if result.status in {"revoked", "expired"}:
        raise HTTPException(status_code=410, detail=f"分享已{result.status}")
    return result


@router.post("/shares")
def create_share(body: ShareIn) -> dict:
    from myagentflow.persistence.chat_message_repositories import count_messages

    if count_messages(body.thread_id) == 0:
        raise HTTPException(status_code=404, detail=f"session {body.thread_id} 没有消息")
    snapshot = _load_messages(body.thread_id)
    token = get_share_store().create(
        body.thread_id,
        ttl_seconds=body.ttl_seconds,
        snapshot=snapshot,
    )
    return {"token": token, "thread_id": body.thread_id, "count": len(snapshot)}


@router.delete("/shares/thread/{thread_id}")
def revoke_thread_shares(thread_id: str) -> dict:
    revoked = get_share_store().revoke_thread(thread_id)
    return {"thread_id": thread_id, "revoked": revoked}


@router.get("/shares/{token}")
def read_share(token: str) -> dict:
    result = _resolve_or_raise(token)
    snapshot = get_share_store().snapshot(token)
    frozen = snapshot is not None
    messages = snapshot if frozen else _load_messages(result.thread_id or "")
    return {
        "thread_id": result.thread_id,
        "messages": messages,
        "count": len(messages),
        "snapshot": frozen,
    }


@router.get("/shares/{token}/export")
def export_share(
    token: str,
    format: str = Query(default="markdown", pattern="^(markdown|json)$"),
) -> Response:
    from myagentflow.collab.export import render_json, render_markdown

    result = _resolve_or_raise(token)
    snapshot = get_share_store().snapshot(token)
    messages = snapshot if snapshot is not None else _load_messages(result.thread_id or "")
    if format == "json":
        return Response(
            content=render_json(result.thread_id or "", messages),
            media_type="application/json",
        )
    return Response(
        content=render_markdown(result.thread_id or "", messages),
        media_type="text/markdown; charset=utf-8",
    )


@router.delete("/shares/{token}")
def revoke_share(token: str) -> dict:
    revoked = get_share_store().revoke(token)
    if revoked == 0:
        raise HTTPException(status_code=404, detail="分享不存在或已吊销")
    return {"token": token, "revoked": True}
