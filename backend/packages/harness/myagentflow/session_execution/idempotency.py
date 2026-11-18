"""一、文件说明
    幂等：同一个请求只执行一次。
    为什么不是「执行完再检查」：两个并发请求会同时通过检查，
    所以必须在执行前就用「占用」把键钉住。

二、目录结构
    packages/harness/myagentflow/session_execution/
    ├── __init__.py
    ├── idempotency.py  ← 本文件
    └── lifecycle.py  运行生命周期：登记、取消、收尾。

三、关键方法
    Entry        幂等键的状态与结果。
    Idempotency  同一 key 只执行一次；重复请求直接返回上次结果。
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass


@dataclass
class Entry:
    """幂等键的状态与结果。"""
    status: str          # running | done
    result: object = None
    at: float = 0.0


class Idempotency:
    """同一 key 只执行一次；重复请求直接返回上次结果。"""
    def __init__(self) -> None:
        self._items: dict[str, Entry] = {}
        self._lock = threading.Lock()

    def begin(self, key: str) -> tuple[str, object]:
        """返回 (状态, 结果)：fresh 可执行；running 请等待；cached 直接用。"""
        with self._lock:
            cur = self._items.get(key)
            if cur is None:
                self._items[key] = Entry("running", at=time.time())
                return "fresh", None
            if cur.status == "running":
                return "running", None
            return "cached", cur.result

    def finish(self, key: str, result: object) -> None:
        with self._lock:
            e = self._items.get(key)
            if e is None:
                return
            e.status, e.result, e.at = "done", result, time.time()
