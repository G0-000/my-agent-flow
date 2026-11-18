"""一、文件说明
    协作账本：任务认领与心跳。
    为什么要版本号：两个人同时点「认领」，后写的那次必须失败，
    否则同一个任务会被执行两遍。

二、目录结构
    packages/harness/myagentflow/collab/
    ├── __init__.py
    ├── ledger.py  ← 本文件
    └── shares.py  分享链接：创建、解析、撤销。

三、关键方法
    Task
    Ledger
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field


@dataclass
class Task:
    id: str
    title: str
    status: str = "open"          # open | claimed | done | failed
    owner: str | None = None
    version: int = 0
    last_seen: float = field(default_factory=time.time)


class Ledger:
    def __init__(self) -> None:
        self._tasks: dict[str, Task] = {}

    def add(self, task: Task) -> None:
        self._tasks[task.id] = task

    def claim(self, task_id: str, owner: str, expected_version: int) -> Task:
        t = self._tasks[task_id]
        if t.status != "open" or t.version != expected_version:
            raise RuntimeError(f"认领失败：status={t.status} version={t.version}")
        t.owner = owner
        t.status = "claimed"
        t.version += 1                 # 版本一变，别人的条件更新就会失败
        t.last_seen = time.time()
        return t

    def heartbeat(self, task_id: str, owner: str) -> None:
        t = self._tasks[task_id]
        if t.owner != owner:
            raise RuntimeError("不是你的任务")
        t.last_seen = time.time()

    def reclaim_stale(self, timeout: float = 120, now: float | None = None) -> list[str]:
        now = now or time.time()
        freed = []
        for t in self._tasks.values():
            if t.status == "claimed" and now - t.last_seen > timeout:
                t.status, t.owner = "open", None
                t.version += 1
                freed.append(t.id)
        return freed
