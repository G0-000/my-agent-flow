"""一、文件说明
    03/02 宿主侧：后台任务表（登记/停止/输出快照）与桥接 token 校验。

二、覆盖
    test_register_get_list()       任务登记、按 id 取、running_only 过滤、摘要形状。
    test_stop_task()               停止运行中的进程并置 cancelled，重复 stop 幂等。
    test_read_output_snapshot()    输出超过 8KB 只回尾部并标 truncated。
    test_bridge_token()            没配 token 一律拒绝；配了才按常量时间比对。

三、运行
    uv run pytest tests/chapters/test_ch03_02_host_direct.py -q
"""

from __future__ import annotations

import subprocess


def test_register_get_list(tmp_path):
    """任务登记、按 id 取、running_only 过滤、摘要形状。"""
    from myagentflow.tools.host_direct.background_bash import (
        BackgroundBashTask,
        get_task,
        list_tasks,
        mark,
        new_task_id,
        register_task,
        task_to_summary,
    )

    task = BackgroundBashTask(
        task_id=new_task_id(),
        command="sleep 1",
        description="demo",
        output_path=tmp_path / "out.log",
        thread_id="t1",
    )
    register_task(task)
    assert get_task(task.task_id) is task
    assert task in list_tasks(running_only=True)
    summary = task_to_summary(task)
    assert summary["status"] == "running" and summary["cancellable"] is True

    mark(task, status="completed", exit_code=0)
    assert list_tasks(running_only=True) == []
    assert task_to_summary(task)["status"] == "resultPending"


def test_stop_task(tmp_path):
    """停止运行中的进程并置 cancelled，重复 stop 幂等。"""
    from myagentflow.tools.host_direct.background_bash import (
        BackgroundBashTask,
        new_task_id,
        register_task,
        stop_task,
    )

    proc = subprocess.Popen(["sleep", "5"])
    task = BackgroundBashTask(
        task_id=new_task_id(),
        command="sleep 5",
        description="stop me",
        output_path=tmp_path / "out.log",
        proc=proc,
    )
    register_task(task)

    stopped = stop_task(task.task_id)
    assert stopped is not None
    assert stopped.status == "cancelled"
    proc.wait(timeout=5)
    assert proc.returncode is not None

    # 再停一次：已经是终态，不能再改退出码
    assert stop_task(task.task_id).exit_code == -1


def test_read_output_snapshot(tmp_path):
    """输出超过 8KB 只回尾部并标 truncated。"""
    from myagentflow.tools.host_direct.background_bash import (
        BACKGROUND_BASH_OUTPUT_MAX_BYTES,
        BackgroundBashTask,
        new_task_id,
        read_output_snapshot,
    )

    out = tmp_path / "out.log"
    payload = "a" * (BACKGROUND_BASH_OUTPUT_MAX_BYTES + 100)
    out.write_text(payload, encoding="utf-8")
    task = BackgroundBashTask(
        task_id=new_task_id(), command="echo", description="big", output_path=out
    )
    snap = read_output_snapshot(task)
    assert snap["truncated"] is True
    assert len(snap["output"]) == BACKGROUND_BASH_OUTPUT_MAX_BYTES
    assert snap["output"].endswith("a")


def test_bridge_token(monkeypatch):
    """没配 token 一律拒绝；配了才按常量时间比对。"""
    from myagentflow.tools.host_direct.bridge_auth import verify_bridge_token

    monkeypatch.delenv("MYAF_BRIDGE_TOKEN", raising=False)
    assert verify_bridge_token("anything") is False

    monkeypatch.setenv("MYAF_BRIDGE_TOKEN", "s3cret")
    assert verify_bridge_token("s3cret") is True
    assert verify_bridge_token("wrong") is False
    assert verify_bridge_token(None) is False
