"""第 03.3 / 03.4 章：宿主命令与文件工具的最小行为测试。

覆盖：
- run_command：同步执行、退出码、超时杀进程
- 文件工具：读写列目录都限定在 workspace 内，越界路径被拒
- 后台任务：启动 → 读输出 → 停止，工具层与任务表状态一致
"""

from __future__ import annotations

import json
import time

import pytest


@pytest.fixture(autouse=True)
def _workspace(monkeypatch, tmp_path):
    monkeypatch.setenv("MYAF_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.delenv("MYAF_BRIDGE_TOKEN", raising=False)


def test_run_command_returns_exit_code():
    from myagentflow.tools.builtins.shell import run_command

    out = run_command("echo hi")
    assert out.startswith("exit=0")
    assert "hi" in out


def test_run_command_timeout(monkeypatch):
    from myagentflow.tools.builtins.shell import run_command

    out = run_command("sleep 5", timeout=1)
    assert "timeout after 1s" in out


def test_file_tools_confine_to_workspace(tmp_path):
    from myagentflow.tools.builtins.workspace_files import (
        list_dir,
        read_file,
        write_file,
    )

    assert "written" in write_file("sub/a.txt", "line1\nline2\nline3")
    assert read_file("sub/a.txt", offset=1, limit=2) == "line2\nline3"
    assert "d sub" in list_dir(".")

    with pytest.raises(PermissionError):
        write_file("../escape.txt", "x")
    with pytest.raises(PermissionError):
        read_file("/etc/passwd")


def test_background_lifecycle():
    from myagentflow.tools.builtins.shell import (
        get_background_output,
        start_background_command,
    )

    started = start_background_command("echo bg-done")
    task_id = started.splitlines()[0].split(": ", 1)[1]

    # 等进程把输出写进文件，再读快照
    deadline = time.time() + 5
    snap: dict = {}
    while time.time() < deadline:
        snap = json.loads(get_background_output(task_id))
        if snap["status"] != "running":
            break
        time.sleep(0.05)

    assert "bg-done" in snap["output"]
    assert snap["status"] in {"completed", "resultPending"}


def test_background_stop():
    from myagentflow.tools.builtins.shell import (
        start_background_command,
        stop_background_command,
    )

    started = start_background_command("sleep 30")
    task_id = started.splitlines()[0].split(": ", 1)[1]

    stopped = stop_background_command(task_id)
    assert "cancelled" in stopped or "completed" in stopped
