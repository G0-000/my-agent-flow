"""一、文件说明
    后台命令任务表：登记、查询、停止、输出快照。
    为什么只做「内存表」：本章先把任务生命周期与 404/409 语义讲清；
    真正的进程启动在工具层，落库/跨进程查询属于后续 Gateway 章节。

二、目录结构
    packages/harness/myagentflow/tools/host_direct/
    ├── __init__.py
    ├── background_bash.py  ← 本文件：后台任务登记与查询
    ├── bridge_auth.py      桥接鉴权：浏览器桥 / CUA 桥共用的 token 校验
    └── workspace_path_guard.py  宿主路径守卫：解析 + 可切换策略

三、关键方法
    BackgroundBashTask      一次后台命令的事实：id、命令、输出文件、状态、进程。
    new_task_id()           生成 12 位十六进制任务 id。
    register_task()         登记任务；同 id 覆盖（重放/恢复时用）。
    get_task()              按 id 取任务；不存在返回 None。
    mark()                  改状态与退出码，只在首次结束时写 ended_at。
    stop_task()             杀进程并置 cancelled；不存在返回 None。
    list_tasks()            列任务，可按 running_only / thread_id 过滤。
    task_to_summary()       给状态面板的最小摘要。
    read_output_snapshot()  读输出文件尾部（最多 8192 字节），标是否截断。
"""
from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

# 输出只回灌尾部 8KB：后台任务可能跑几小时，全量塞回模型会撑爆上下文
BACKGROUND_BASH_OUTPUT_MAX_BYTES = 8192


@dataclass
class BackgroundBashTask:
    """一次后台命令的事实：id、命令、输出文件、状态、进程。"""
    task_id: str
    command: str
    description: str
    output_path: Path
    status: str = "running"          # running | completed | failed | stopped | cancelled
    exit_code: int | None = None
    error: str = ""
    proc: object | None = None
    started_at: float = field(default_factory=time.time)
    ended_at: float | None = None
    thread_id: str = ""


_LOCK = threading.Lock()
_TASKS: dict[str, BackgroundBashTask] = {}


def new_task_id() -> str:
    """生成 12 位十六进制任务 id。"""
    return uuid.uuid4().hex[:12]


def register_task(task: BackgroundBashTask) -> None:
    """登记任务；同 id 覆盖（重放/恢复时用）。"""
    with _LOCK:
        _TASKS[task.task_id] = task


def get_task(task_id: str) -> BackgroundBashTask | None:
    """按 id 取任务；不存在返回 None。"""
    with _LOCK:
        return _TASKS.get(task_id)


def mark(
    task: BackgroundBashTask,
    *,
    status: str,
    exit_code: int | None = None,
    error: str = "",
) -> None:
    """改状态与退出码，只在首次结束时写 ended_at。"""
    task.status = status
    task.exit_code = exit_code
    if error:
        task.error = error
    if status != "running" and task.ended_at is None:
        task.ended_at = time.time()


def stop_task(task_id: str) -> BackgroundBashTask | None:
    """杀进程并置 cancelled；不存在返回 None。

    只停止 running 的任务：已结束的任务再 stop 是 no-op，不该改掉真实退出码。
    """
    task = get_task(task_id)
    if task is None:
        return None
    proc = task.proc
    if proc is not None and task.status == "running":
        try:
            proc.kill()  # type: ignore[attr-defined]
        except Exception as exc:
            task.error = str(exc)
        mark(task, status="cancelled", exit_code=-1)
    return task


def list_tasks(*, running_only: bool = False, thread_id: str | None = None) -> list[BackgroundBashTask]:
    """列任务，可按 running_only / thread_id 过滤。"""
    with _LOCK:
        items = list(_TASKS.values())
    if thread_id:
        tid = thread_id.strip()
        items = [t for t in items if not t.thread_id or t.thread_id == tid]
    if running_only:
        items = [t for t in items if t.status == "running"]
    items.sort(key=lambda t: t.started_at)
    return items


def task_to_summary(task: BackgroundBashTask) -> dict:
    """给状态面板的最小摘要。"""
    return {
        "workId": task.task_id,
        "kind": "bash",
        "title": (task.description or task.command or task.task_id)[:200],
        "status": "running" if task.status == "running" else (
            "cancelled" if task.status in {"stopped", "cancelled"} else (
                "failed" if task.status == "failed" else "resultPending"
            )
        ),
        "startedAt": int(task.started_at * 1000),
        "endedAt": int(task.ended_at * 1000) if task.ended_at else None,
        "cancellable": bool(task.status == "running"),
        "command": task.command,
        "outputPath": str(task.output_path),
        "exitCode": task.exit_code,
    }


def read_output_snapshot(task: BackgroundBashTask) -> dict:
    """读输出文件尾部（最多 8192 字节），标是否截断。"""
    text = ""
    truncated = False
    try:
        raw = task.output_path.read_bytes() if task.output_path.is_file() else b""
        if len(raw) > BACKGROUND_BASH_OUTPUT_MAX_BYTES:
            truncated = True
            raw = raw[-BACKGROUND_BASH_OUTPUT_MAX_BYTES:]
        text = raw.decode("utf-8", errors="replace")
    except OSError as exc:
        return {"kind": "read_failed", "workId": task.task_id, "code": str(exc)}

    status_map = {
        "running": "running",
        "completed": "completed",
        "failed": "failed",
        "stopped": "cancelled",
        "cancelled": "cancelled",
    }
    return {
        "kind": "output",
        "workId": task.task_id,
        "status": status_map.get(task.status, "completed"),
        "output": text,
        "truncated": truncated,
        "outputPath": str(task.output_path),
    }
