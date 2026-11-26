"""一、文件说明
    审批单：一次危险调用一张单子。
    为什么用 deadline 而不是定时器：
    重启后定时器全丢，deadline 存在表里，进程起来照样能判过期。

二、目录结构
    packages/harness/myagentflow/sandbox/
    ├── __init__.py
    ├── approvals.py  ← 本文件
    └── policy.py  沙箱策略：allow / ask / deny。

三、关键方法
    Approval       一条待审批的工具调用：run、工具、参数、状态、截止时间。
    ApprovalStore  内存审批队列：创建、通过、拒绝、清理超时项。
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field

# 审批单的终态：pending 之外四个。expired 也是终态，过期后不能再被批准
ALLOWED = {"approved", "rejected", "expired", "cancelled"}

_STORE = None


def get_approval_store() -> ApprovalStore:
    """进程内审批单例；API 与工具中间件共用同一份。"""
    global _STORE
    if _STORE is None:
        _STORE = ApprovalStore()
    return _STORE


@dataclass
class Approval:
    """一条待审批的工具调用：run、工具、参数、状态、截止时间。"""
    run_id: str
    tool: str
    args: dict
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:10])
    status: str = "pending"
    deadline: float = field(default_factory=lambda: time.time() + 300)


class ApprovalStore:
    """内存审批队列：创建、通过、拒绝、清理超时项。"""
    def __init__(self) -> None:
        self._items: dict[str, Approval] = {}

    def create(self, run_id: str, tool: str, args: dict, ttl: int = 300) -> Approval:
        ap = Approval(run_id=run_id, tool=tool, args=dict(args), deadline=time.time() + ttl)
        self._items[ap.id] = ap
        return ap

    def find_pending(self, run_id: str, tool: str, args: dict) -> Approval | None:
        """同一 run/工具/参数只保留一张 pending 单，避免模型重试刷屏。"""
        for ap in self._items.values():
            if ap.status == "pending" and ap.run_id == run_id and ap.tool == tool and ap.args == dict(args):
                return ap
        return None

    def get(self, approval_id: str) -> Approval | None:
        """按 id 取审批单；不存在返回 None。"""
        return self._items.get(approval_id)

    def list_pending(self, run_id: str | None = None) -> list[Approval]:
        """列 pending 审批单；可按 run_id 过滤。"""
        items = [a for a in self._items.values() if a.status == "pending"]
        if run_id:
            items = [a for a in items if a.run_id == run_id]
        return sorted(items, key=lambda a: a.deadline)

    def is_approved(self, approval_id: str, tool: str, args: dict, now: float | None = None) -> bool:
        """审批单必须已批准、未过期，且工具与参数完全一致。"""
        ap = self._items.get(approval_id)
        if ap is None or ap.status != "approved":
            return False
        if now is not None and now > ap.deadline:
            ap.status = "expired"
            return False
        return ap.tool == tool and ap.args == dict(args)

    def resolve(self, approval_id: str, decision: str, now: float | None = None) -> Approval:
        ap = self._items[approval_id]
        now = now or time.time()
        if ap.status != "pending":
            raise RuntimeError(f"审批单已是终态：{ap.status}")
        if decision not in {"approved", "rejected"}:
            raise ValueError(f"非法决定：{decision}")
        if now > ap.deadline:
            ap.status = "expired"          # 超时优先于用户点按钮
        else:
            ap.status = decision
        return ap

    def cancel_run(self, run_id: str) -> int:
        n = 0
        for ap in self._items.values():
            if ap.run_id == run_id and ap.status == "pending":
                ap.status = "cancelled"; n += 1
        return n
