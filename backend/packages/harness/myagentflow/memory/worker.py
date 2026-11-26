"""一、文件说明
    记忆抽取后台 worker：定时把到期批次交给 updater，失败退避。
    为什么需要它：队列只是「待办清单」，没有 worker 就永远等不到下一次抽取；
    放在聊天请求里又会把抽取延迟加给用户。

二、目录结构
    packages/harness/myagentflow/memory/
    ├── queue.py    防抖队列
    ├── updater.py  抽取 + 写回
    └── worker.py   ← 本文件：进程内后台线程 + 聊天入队入口

三、关键方法
    enqueue_exchange()  一轮问答结束后入队；空回答不入队
    MemoryWorker.start()  幂等启动；重复调用返回 False
    MemoryWorker.stop()   停止并等待线程退出
    MemoryWorker.tick()   跑一次到期批次；测试可直接调用，不必等线程
"""
from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from typing import Any

from myagentflow.memory.queue import MemoryUpdateQueue
from myagentflow.memory.updater import flush_queue

logger = logging.getLogger(__name__)

_queue: MemoryUpdateQueue | None = None
_queue_lock = threading.Lock()
_worker: MemoryWorker | None = None
_worker_lock = threading.Lock()


def get_queue() -> MemoryUpdateQueue:
    """进程内单例队列；聊天与 worker 必须用同一个，否则入队后没人消费。"""
    global _queue
    with _queue_lock:
        if _queue is None:
            _queue = MemoryUpdateQueue()
        return _queue


def reset_queue() -> None:
    """测试用：丢掉当前队列，避免用例之间串批次。"""
    global _queue
    with _queue_lock:
        _queue = None


def enqueue_exchange(
    namespace: str,
    thread_id: str,
    user_text: str,
    assistant_text: str,
) -> Any | None:
    """一轮问答结束后登记待抽取文本；空回答直接跳过，不产生空批次。"""
    body = (assistant_text or "").strip()
    if not body:
        return None
    text = f"用户：{(user_text or '').strip()}\n助手：{body}"
    return get_queue().enqueue(namespace, text, thread_id=thread_id)


class MemoryWorker:
    """进程内 daemon 线程；跨进程需要换持久化队列与租约。"""

    def __init__(
        self,
        model_factory: Callable[[], Any],
        *,
        interval: float | None = None,
        queue: MemoryUpdateQueue | None = None,
    ) -> None:
        self._model_factory = model_factory
        if interval is None:
            from myagentflow.config.app_config import get_app_config

            interval = get_app_config().memory.worker_interval
        self.interval = max(0.1, float(interval))
        self.queue = queue or get_queue()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._start_lock = threading.Lock()
        self.last_stats: dict[str, Any] | None = None

    def start(self) -> bool:
        """幂等启动；已经在跑就返回 False，避免测试或热重载叠出多条线程。"""
        with self._start_lock:
            if self._thread is not None and self._thread.is_alive():
                return False
            self._stop.clear()
            self._thread = threading.Thread(
                target=self._run,
                name="myaf-memory-worker",
                daemon=True,
            )
            self._thread.start()
            return True

    def stop(self, timeout: float = 2.0) -> None:
        self._stop.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout=timeout)
        self._thread = None

    def _run(self) -> None:
        while not self._stop.wait(self.interval):
            try:
                self.tick()
            except Exception:  # 后台线程不能因为一次失败就死掉
                logger.exception("memory worker tick failed")

    def tick(self, now: float | None = None) -> dict[str, Any]:
        """跑一次到期批次；模型建不起来时保留队列，等下一轮。"""
        try:
            model = self._model_factory()
        except Exception:
            logger.exception("memory worker: model unavailable")
            return {"processed": 0, "written": 0, "failed": 0, "skipped": 0}
        stats = flush_queue(self.queue, model, now=now)
        self.last_stats = stats
        return stats


def start_worker(
    model_factory: Callable[[], Any],
    *,
    interval: float | None = None,
) -> MemoryWorker:
    """取全局 worker 并启动；模型工厂延迟到 tick 时才调用。

    interval 缺省读 config.yaml 的 ``memory.worker_interval``（部署可调，不硬编码）。
    """
    global _worker
    with _worker_lock:
        if _worker is None:
            _worker = MemoryWorker(model_factory, interval=interval)
        _worker.start()
        return _worker


def stop_worker() -> None:
    global _worker
    with _worker_lock:
        if _worker is not None:
            _worker.stop()
            _worker = None
