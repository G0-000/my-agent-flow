"""审批单：一次危险调用一张单子。

为什么用 deadline 而不是定时器：
重启后定时器全丢，deadline 存在表里，进程起来照样能判过期。
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field

# 审批单的终态：pending 之外四个。expired 也是终态，过期后不能再被批准
ALLOWED = {"approved", "rejected", "expired", "cancelled"}


@dataclass
class Approval:
    run_id: str
    tool: str
    args: dict
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:10])
    status: str = "pending"
    deadline: float = field(default_factory=lambda: time.time() + 300)


class ApprovalStore:
    def __init__(self) -> None:
        self._items: dict[str, Approval] = {}

    def create(self, run_id: str, tool: str, args: dict, ttl: int = 300) -> Approval:
        ap = Approval(run_id=run_id, tool=tool, args=dict(args), deadline=time.time() + ttl)
        self._items[ap.id] = ap
        return ap

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
