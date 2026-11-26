"""一、文件说明
    长期记忆的异步更新队列：防抖合并，按时间到期出队。
    为什么不让聊天请求里直接写记忆：抽取要额外调一次模型，放在回答链路上会拖慢首字；
    而且同一 thread 连着几轮都在聊同一件事，逐轮抽取会写一堆重复 atom。

二、目录结构
    packages/harness/myagentflow/memory/
    ├── store.py           atom 存储
    ├── facade.py          对外的 remember/recall/consolidate
    ├── consolidate.py     巩固与合并
    ├── queue.py           ← 本文件：防抖队列
    └── updater.py         抽取 + 写回

三、关键方法
    MemoryUpdateQueue.enqueue()  登记一段待抽取文本；同键合并、重置到期时间
    MemoryUpdateQueue.due()      取出到期批次；不出队，等 ack 才删
    MemoryUpdateQueue.ack()      抽取成功后出队；失败由调用方决定重试或丢弃
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field


@dataclass
class PendingUpdate:
    """一段待抽取的文本；同 namespace + thread 合并成一条。"""

    key: str
    namespace: str
    thread_id: str
    text: str = ""
    rounds: int = 0
    attempts: int = 0
    due_at: float = 0.0
    extra: dict = field(default_factory=dict)


class MemoryUpdateQueue:
    """进程内防抖队列；跨进程需要换持久化实现。"""

    def __init__(self, *, debounce_seconds: float = 3.0, max_batch: int = 20) -> None:
        self.debounce_seconds = max(0.0, float(debounce_seconds))
        self.max_batch = max(1, int(max_batch))
        self._items: dict[str, PendingUpdate] = {}
        self._lock = threading.Lock()

    @staticmethod
    def make_key(namespace: str, thread_id: str) -> str:
        return f"{namespace}|{thread_id}"

    def enqueue(
        self,
        namespace: str,
        text: str,
        *,
        thread_id: str = "",
        now: float | None = None,
    ) -> PendingUpdate:
        """登记文本；同键再入队只追加内容并顺延到期时间。"""
        ns = (namespace or "").strip()
        if not ns:
            raise ValueError("namespace required")
        body = (text or "").strip()
        if not body:
            raise ValueError("text required")
        now = time.time() if now is None else float(now)
        key = self.make_key(ns, thread_id)
        with self._lock:
            item = self._items.get(key)
            if item is None:
                item = PendingUpdate(key=key, namespace=ns, thread_id=thread_id, text=body)
                self._items[key] = item
            else:
                item.text = f"{item.text}\n{body}" if item.text else body
                item.rounds += 1
            item.due_at = now + self.debounce_seconds
            return item

    def due(self, now: float | None = None) -> list[PendingUpdate]:
        """取出到期批次；不删除，调用方 ack 后才出队。"""
        now = time.time() if now is None else float(now)
        with self._lock:
            ready = [i for i in self._items.values() if i.due_at <= now]
            ready.sort(key=lambda i: i.due_at)
            return ready[: self.max_batch]

    def ack(self, item: PendingUpdate) -> None:
        """成功写回后出队；只删同一个对象，避免删掉新入队的同键内容。"""
        with self._lock:
            if self._items.get(item.key) is item:
                del self._items[item.key]

    def fail(self, item: PendingUpdate) -> None:
        """抽取失败：计数加一，稍后再试；调用方用 retry_delay 控制节奏。"""
        item.attempts += 1

    def retry_later(self, item: PendingUpdate, *, delay: float = 5.0, now: float | None = None) -> None:
        """失败退避：重新排期，仍留在队列里。"""
        now = time.time() if now is None else float(now)
        item.due_at = now + max(0.0, float(delay))

    def pending_count(self) -> int:
        with self._lock:
            return len(self._items)

    def clear(self) -> None:
        with self._lock:
            self._items.clear()
