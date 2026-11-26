"""审批 API：列 pending、批准/拒绝。审批单进程内共享。"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()


class DecisionIn(BaseModel):
    decision: str
    run_id: str = ""


def _store():
    from myagentflow.sandbox.approvals import get_approval_store

    return get_approval_store()


def _to_dict(ap) -> dict:
    return {
        "id": ap.id,
        "run_id": ap.run_id,
        "tool": ap.tool,
        "args": ap.args,
        "status": ap.status,
        "deadline": ap.deadline,
    }


@router.get("/approvals")
def list_approvals(run_id: str = "") -> dict:
    return {"items": [_to_dict(ap) for ap in _store().list_pending(run_id or None)]}


@router.post("/approvals/{approval_id}")
def decide(approval_id: str, body: DecisionIn) -> dict:
    ap = _store().get(approval_id)
    if ap is None:
        raise HTTPException(status_code=404, detail=f"审批单不存在：{approval_id}")
    try:
        ap = _store().resolve(approval_id, body.decision)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _to_dict(ap)
