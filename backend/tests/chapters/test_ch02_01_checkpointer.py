"""一、文件说明
    02/01 检查点：单例、建表、空线程读取。

二、覆盖
    test_sqlite_setup_and_singleton()  两次取检查点返回同一对象，且 setup() 建出了 checkpoints 表。
    test_read_unknown_thread()         读不存在的线程返回 None，不抛异常。
    test_omit_transcript_on_put()      正常轮次写入前把 messages / ui_messages 清空。
    test_keep_messages_for_unresolved_tool_call()  工具没配对的轮次必须保留 messages。
    test_omit_switch_off()             开关关闭时原样写入，不剥对话。

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


class _RecordingSaver:
    """记录 put 收到什么的假 saver：只验证「写之前被改成了什么」。"""

    def __init__(self) -> None:
        self.checkpoint = None

    def put(self, config, checkpoint, metadata, new_versions):
        self.checkpoint = checkpoint

    async def aput(self, config, checkpoint, metadata, new_versions):
        self.checkpoint = checkpoint


def test_omit_transcript_on_put(monkeypatch):
    """正常轮次（工具都配对）写入前把两个对话通道清空，其他通道保留。"""
    monkeypatch.delenv("MYAF_CHECKPOINT_OMIT_TRANSCRIPT", raising=False)
    from langchain_core.messages import AIMessage, HumanMessage
    from myagentflow.agents.checkpointer.omit_transcript import (
        OmitTranscriptCheckpointer,
    )

    inner = _RecordingSaver()
    cp = OmitTranscriptCheckpointer(inner)
    cp.put(
        {"configurable": {"thread_id": "t1"}},
        {
            "channel_values": {
                "messages": [HumanMessage(content="hi"), AIMessage(content="ok")],
                "ui_messages": [{"type": "human"}],
                "plan": {"steps": 1},
            }
        },
        {},
        {},
    )
    assert inner.checkpoint["channel_values"]["messages"] == []
    assert inner.checkpoint["channel_values"]["ui_messages"] == []
    assert inner.checkpoint["channel_values"]["plan"] == {"steps": 1}   # 非对话通道不许动


def test_keep_messages_for_unresolved_tool_call(monkeypatch):
    """AI 带 tool_call、还没有对应 ToolMessage 时，messages 必须原样保留。"""
    monkeypatch.delenv("MYAF_CHECKPOINT_OMIT_TRANSCRIPT", raising=False)
    from langchain_core.messages import AIMessage
    from myagentflow.agents.checkpointer.omit_transcript import (
        OmitTranscriptCheckpointer,
    )

    messages = [
        AIMessage(
            content="",
            tool_calls=[{"name": "echo", "args": {"text": "x"}, "id": "call-1"}],
        )
    ]
    inner = _RecordingSaver()
    cp = OmitTranscriptCheckpointer(inner)
    cp.put({"configurable": {"thread_id": "t1"}}, {"channel_values": {"messages": messages}}, {}, {})
    assert inner.checkpoint["channel_values"]["messages"] == messages


def test_omit_switch_off(monkeypatch):
    """开关设 0 时，put 收到的 checkpoint 保持原样。"""
    monkeypatch.setenv("MYAF_CHECKPOINT_OMIT_TRANSCRIPT", "0")
    from langchain_core.messages import HumanMessage
    from myagentflow.agents.checkpointer.omit_transcript import (
        OmitTranscriptCheckpointer,
    )

    messages = [HumanMessage(content="hi")]
    inner = _RecordingSaver()
    cp = OmitTranscriptCheckpointer(inner)
    cp.put({"configurable": {"thread_id": "t1"}}, {"channel_values": {"messages": messages}}, {}, {})
    assert inner.checkpoint["channel_values"]["messages"] == messages
