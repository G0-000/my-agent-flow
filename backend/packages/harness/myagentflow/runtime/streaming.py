"""一、文件说明
    把 LangGraph 的 astream_events 收敛成我们自己的事件。

二、目录结构
    packages/harness/myagentflow/runtime/
    ├── __init__.py
    ├── events.py  流式事件：统一形状 + SSE 序列化。
    └── streaming.py  ← 本文件

三、关键方法
    stream_graph()
"""
from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from myagentflow.runtime.events import EventStream


async def stream_graph(graph: Any, payload: dict, config: dict) -> AsyncIterator[str]:
    stream = EventStream()
    try:
        async for raw in graph.astream_events(payload, config=config, version="v2"):
            kind = raw.get("event")
            if kind == "on_chat_model_stream":
                chunk = raw["data"].get("chunk")
                text = getattr(chunk, "content", "") or ""
                if text:
                    yield stream.emit("token", text=text).to_sse()
            elif kind == "on_tool_end":
                yield stream.emit("tool", name=raw.get("name"), output=str(raw["data"].get("output"))[:500]).to_sse()
        yield stream.emit("done").to_sse()
    except Exception as exc:  # 流里抛异常会让前端「卡住」，必须显式发 error
        yield stream.emit("error", message=str(exc)).to_sse()
