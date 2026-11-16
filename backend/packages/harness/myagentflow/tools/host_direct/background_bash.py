"""后台命令：启动、查询、终止。

为什么 poll 要区分 404/409：
404 = 你问的这个 id 我从没见过（客户端 bug）；
409 = 见过但已经退出（正常的生命周期结束）。两者混在一起就没法排查。
"""
from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from typing import Any


@dataclass
class BgProc:
    proc: subprocess.Popen
    stdout_path: str
    _log: list[str] = field(default_factory=list)


class BgManager:
    def __init__(self) -> None:
        self._procs: dict[str, BgProc] = {}

    def start(self, cmd: str, stdout_path: str) -> str:
        import uuid

        run_id = uuid.uuid4().hex[:8]
        proc = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        self._procs[run_id] = BgProc(proc=proc, stdout_path=stdout_path)
        return run_id

    def poll(self, run_id: str) -> dict[str, Any]:
        rec = self._procs.get(run_id)
        if rec is None:
            raise LookupError("no such background process")     # → 404
        if rec.proc.poll() is None:
            return {"status": "running", "pid": rec.proc.pid, "stdout": rec.stdout_path}
        return {"status": "exited", "code": rec.proc.returncode}  # → 409 语义

    def kill(self, run_id: str) -> None:
        rec = self._procs.get(run_id)
        if rec is None:
            raise LookupError("no such background process")
        if rec.proc.poll() is None:
            rec.proc.terminate()
