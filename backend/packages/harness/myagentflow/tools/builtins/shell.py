"""宿主命令工具：同步执行、后台启动、读输出、停止。"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from myagentflow.tools import large_result_store
from myagentflow.tools.host_direct import background_bash as bg
from myagentflow.tools.host_direct.workspace_path_guard import Policy, resolve
from myagentflow.tools.registry import ToolRegistry, ToolSpec
from myagentflow.tools.tool_output_truncation import formatted_truncate_tool_output

_DEFAULT_TIMEOUT = 10
_MAX_OUTPUT_TOKENS = 4000


def _cwd() -> Path:
    root = Path(os.getenv("MYAF_WORKSPACE") or ".myaf/workspace").expanduser()
    root.mkdir(parents=True, exist_ok=True)
    return resolve(".", root, Policy.confine).path


def run_command(command: str, timeout: int = _DEFAULT_TIMEOUT) -> str:
    """在工作区同步执行命令；超时杀进程，输出截断后回灌。"""
    try:
        proc = subprocess.run(
            command,
            shell=True,
            cwd=_cwd(),
            capture_output=True,
            text=True,
            timeout=max(1, int(timeout)),
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        out = (exc.stdout or "") + (exc.stderr or "")
        return f"ERROR: timeout after {timeout}s\n{out}"[:20_000]
    raw = f"exit={proc.returncode}\nstdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
    shaped = formatted_truncate_tool_output(raw, _MAX_OUTPUT_TOKENS)
    return large_result_store.maybe_persist(shaped, "run_command", "")


def start_background_command(command: str, description: str = "", thread_id: str = "") -> str:
    """启动后台命令，输出写文件；返回 task id 与输出路径。"""
    task_id = bg.new_task_id()
    out_dir = _cwd() / ".myaf" / "background"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{task_id}.log"
    fh = out_path.open("wb")
    proc = subprocess.Popen(
        command,
        shell=True,
        cwd=_cwd(),
        stdout=fh,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    fh.close()
    task = bg.BackgroundBashTask(
        task_id=task_id,
        command=command,
        description=description,
        output_path=out_path,
        proc=proc,
        thread_id=thread_id,
    )
    bg.register_task(task)
    return f"started: {task_id}\noutput: {out_path}"


def get_background_output(task_id: str) -> str:
    task = bg.get_task(task_id)
    if task is None:
        raise KeyError(f"未知后台任务：{task_id}")
    if task.status == "running" and task.proc is not None:
        rc = task.proc.poll()  # type: ignore[attr-defined]
        if rc is not None:
            bg.mark(task, status="completed" if rc == 0 else "failed", exit_code=rc)
    snap = bg.read_output_snapshot(task)
    return json.dumps(snap, ensure_ascii=False)


def stop_background_command(task_id: str) -> str:
    task = bg.stop_task(task_id)
    if task is None:
        raise KeyError(f"未知后台任务：{task_id}")
    return f"{task.task_id}: {task.status}"


def register_shell(registry: ToolRegistry) -> None:
    registry.register(ToolSpec(
        name="run_command",
        description="在 workspace 同步执行 shell 命令；有超时，输出会截断/落盘。",
        input_schema={
            "type": "object",
            "properties": {
                "command": {"type": "string"},
                "timeout": {"type": "integer", "minimum": 1, "maximum": 120},
            },
            "required": ["command"],
        },
        fn=run_command,
    ))
    registry.register(ToolSpec(
        name="start_background_command",
        description="在 workspace 启动后台命令，立即返回 task id。",
        input_schema={
            "type": "object",
            "properties": {
                "command": {"type": "string"},
                "description": {"type": "string"},
                "thread_id": {"type": "string"},
            },
            "required": ["command"],
        },
        fn=start_background_command,
    ))
    registry.register(ToolSpec(
        name="get_background_output",
        description="读取后台任务输出尾部，并刷新运行状态。",
        input_schema={
            "type": "object",
            "properties": {"task_id": {"type": "string"}},
            "required": ["task_id"],
        },
        fn=get_background_output,
    ))
    registry.register(ToolSpec(
        name="stop_background_command",
        description="停止后台任务。",
        input_schema={
            "type": "object",
            "properties": {"task_id": {"type": "string"}},
            "required": ["task_id"],
        },
        fn=stop_background_command,
    ))
