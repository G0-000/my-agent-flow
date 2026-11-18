"""一、文件说明
    02/01 检查点：单例、建表、空线程读取。

二、覆盖
    test_sqlite_setup_and_singleton()  两次取检查点返回同一对象，且 setup() 建出了 checkpoints 表。
    test_read_unknown_thread()         读不存在的线程返回 None，不抛异常。

三、运行
    uv run pytest tests/chapters/test_ch02_01_checkpointer.py -q
"""
from __future__ import annotations

import sqlite3


def test_sqlite_setup_and_singleton(tmp_path, monkeypatch):
    """两次取检查点返回同一对象，且 setup() 建出了 checkpoints 表。"""
    db = tmp_path / "cp.sqlite"
    monkeypatch.setenv("MYAF_CHECKPOINTER", "sqlite")
    monkeypatch.setenv("MYAF_CHECKPOINT_SQLITE_PATH", str(db))

    from myagentflow.agents.checkpointer import provider

    provider.reset_checkpointer()      # 清掉上一条用例留下的单例
    cp1 = provider.get_checkpointer()
    cp2 = provider.get_checkpointer()
    assert cp1 is cp2                  # 单例

    tables = {
        row[0]
        for row in sqlite3.connect(db).execute(
            "select name from sqlite_master where type='table'"
        )
    }
    assert "checkpoints" in tables     # setup() 真的跑过

    provider.reset_checkpointer()


def test_read_unknown_thread(tmp_path, monkeypatch):
    """读不存在的线程返回 None，不抛异常。"""
    monkeypatch.setenv("MYAF_CHECKPOINTER", "sqlite")
    monkeypatch.setenv("MYAF_CHECKPOINT_SQLITE_PATH", str(tmp_path / "x.sqlite"))

    from myagentflow.agents.checkpointer import provider
    from myagentflow.agents.checkpointer.thread_state_reader import read_thread_state

    provider.reset_checkpointer()
    assert read_thread_state(provider.get_checkpointer(), "nope") is None
    provider.reset_checkpointer()
