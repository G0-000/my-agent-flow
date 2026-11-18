"""一、文件说明
    运行生命周期：登记、取消、收尾。
    为什么用 Event 而不是 bool：取消可能来自另一个线程（HTTP cancel 接口），
    bool 读写没有内存屏障，Event 有。

二、目录结构
    packages/harness/myagentflow/session_execution/
    ├── __init__.py
    ├── idempotency.py  幂等：同一个请求只执行一次。
    └── lifecycle.py  ← 本文件

三、关键方法
    RunRecord
    RunRegistry
"""
from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field

# 允许的终态：running 之外的三个。别把 "failed" 也放进来，否则调用方分不清「取消」和「出错」
ALLOWED_END = {"finished", "cancelled", "error"}


@dataclass
class RunRecord:
    thread_id: str
    run_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    status: str = "running"
    started_at: float = field(default_factory=time.time)
    ended_at: float | None = None
    cancelled: threading.Event = field(default_factory=threading.Event)


class RunRegistry:
    def __init__(self) -> None:
        self._runs: dict[str, RunRecord] = {}
        self._lock = threading.RLock()

    def start(self, thread_id: str) -> RunRecord:
        """开一个 run。同线程已有活跃 run 时直接拒绝：两条 run 会抢写同一个 checkpoint。"""
        with self._lock:
            active = self.active_for_thread(thread_id)
            if active is not None:
                raise RuntimeError(f"线程 {thread_id} 已有活跃 run：{active.run_id}")
            rec = RunRecord(thread_id=thread_id)
            self._runs[rec.run_id] = rec
            return rec

    def active_for_thread(self, thread_id: str) -> RunRecord | None:
        for rec in self._runs.values():
            if rec.thread_id == thread_id and rec.status == "running":
                return rec
        return None

    def cancel(self, run_id: str) -> bool:
        with self._lock:
            rec = self._runs.get(run_id)
            if rec is None or rec.status != "running":
                return False
            rec.cancelled.set()   # 只发信号，真正的收尾由执行方做
            return True

    def is_cancelled(self, run_id: str) -> bool:
        rec = self._runs.get(run_id)
        return bool(rec and rec.cancelled.is_set())

    def finish(self, run_id: str, status: str = "finished") -> None:
        if status not in ALLOWED_END:
            raise ValueError(f"非法终态：{status}")
        with self._lock:
            rec = self._runs.get(run_id)
            if rec is None:
                return
            if rec.cancelled.is_set() and status == "finished":
                status = "cancelled"   # 取消过的 run 不许报成功
            rec.status = status
            rec.ended_at = time.time()
