"""一、文件说明
    02/03 CLI 与 stdio：命令行参数分发、stdin/stdout 一行一答。

二、覆盖
    test_stdio_ping()             ping 返回 pong，id 原样带回。
    test_stdio_state_unknown()     state 读不存在的线程返回 None，不抛异常。
    test_stdio_unknown_method()    未知方法回 error，id 不丢。
    test_serve_bad_json()          坏行回 error，且后续好行仍能处理。
    test_cli_state(capsys)         CLI state 子命令走通，输出 JSON null。

三、运行
    uv run pytest tests/chapters/test_ch02_03_cli_stdio.py -q
"""

from __future__ import annotations

import io
import json


def test_stdio_ping():
    """ping 返回 pong，id 原样带回。"""
    from myagentflow.app_server.stdio import handle

    resp = handle({"id": 1, "method": "ping"})
    assert resp == {"id": 1, "result": "pong"}


def test_stdio_state_unknown(monkeypatch, tmp_path):
    """state 读不存在的线程返回 None，不抛异常。"""
    monkeypatch.setenv("MYAF_CHECKPOINTER", "sqlite")
    monkeypatch.setenv("MYAF_CHECKPOINT_SQLITE_PATH", str(tmp_path / "cp.sqlite"))
    from myagentflow.app_server.stdio import handle

    resp = handle({"id": 2, "method": "state", "params": {"thread_id": "no-such"}})
    assert resp == {"id": 2, "result": None}


def test_stdio_unknown_method():
    """未知方法回 error，id 不丢。"""
    from myagentflow.app_server.stdio import handle

    resp = handle({"id": 3, "method": "chat/send"})
    assert resp["id"] == 3 and "未知方法" in resp["error"]


def test_serve_bad_json():
    """坏行回 error，且后续好行仍能处理：一行坏不能拖垮整个管道。"""
    from myagentflow.app_server.stdio import serve

    stdin = io.StringIO('not-json\n{"id":4,"method":"ping"}\n')
    stdout = io.StringIO()
    serve(stdin=stdin, stdout=stdout)
    lines = [json.loads(x) for x in stdout.getvalue().splitlines()]
    assert "error" in lines[0] and lines[1] == {"id": 4, "result": "pong"}


def test_cli_state(capsys, monkeypatch, tmp_path):
    """CLI state 子命令走通，输出 JSON null。"""
    monkeypatch.setenv("MYAF_CHECKPOINTER", "sqlite")
    monkeypatch.setenv("MYAF_CHECKPOINT_SQLITE_PATH", str(tmp_path / "cp.sqlite"))
    from myagentflow.cli.main import main

    assert main(["state", "--thread", "no-such"]) == 0
    assert capsys.readouterr().out.strip() == "null"
