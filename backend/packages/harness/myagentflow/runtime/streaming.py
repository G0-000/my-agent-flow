"""一、文件说明
    把 LangGraph 的 astream_events 收敛成我们自己的事件。

二、目录结构
    packages/harness/myagentflow/runtime/
    ├── __init__.py
    ├── events.py  流式事件：统一形状 + SSE 序列化。
    └── streaming.py  ← 本文件

三、关键方法
    stream_graph()  把 LangGraph 事件流转成 SSE 文本块，异常收敛成 error 事件；
                    可选把最终文本/错误交给调用方，用于落库和 run 收尾。
"""
from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Callable
from typing import Any

from myagentflow.runtime.events import EventStream

logger = logging.getLogger(__name__)


async def stream_graph(
    graph: Any,
    payload: dict,
    config: dict,
    *,
    on_final: Callable[[str], None] | None = None,
    on_error: Callable[[str], None] | None = None,
    should_cancel: Callable[[], bool] | None = None,
    on_cancel: Callable[[], None] | None = None,
) -> AsyncIterator[str]:
    """把 LangGraph 事件流转成 SSE 文本块，异常收敛成 error 事件。

    Args:
        on_final: 正常结束时回调最终文本；空文本也会回调，由调用方决定是否写库。
        on_error: 异常时回调错误文本；回调本身失败不能掩盖原错误。
        should_cancel: 每处理一个图事件前检查一次；返回 True 就发 cancelled 并结束。
        on_cancel: 取消时回调一次，由调用方落 run 终态。
    """
    stream = EventStream()
    parts: list[str] = []
    try:
        async for raw in graph.astream_events(payload, config=config, version="v2"):
            if should_cancel is not None and should_cancel():
                if on_cancel is not None:
                    on_cancel()
                yield stream.emit("cancelled").to_sse()
                return
            kind = raw.get("event")
            if kind == "on_chat_model_stream":
                chunk = raw["data"].get("chunk")
                text = getattr(chunk, "content", "") or ""
                if text:
                    parts.append(text)
                    yield stream.emit("token", text=text).to_sse()
            elif kind == "on_tool_end":
                yield stream.emit(
                    "tool",
                    name=raw.get("name"),
                    output=str(raw["data"].get("output"))[:500],
                ).to_sse()
        final_text = "".join(parts).strip()
        if on_final is not None:
            try:
                on_final(final_text)
            except Exception as exc:  # 落库失败不能伪装成模型回答成功
                if on_error is not None:
                    on_error(str(exc))
                yield stream.emit("error", message=f"final callback failed: {exc}").to_sse()
                return
        yield stream.emit("done").to_sse()
    except Exception as exc:  # 流里抛异常会让前端「卡住」，必须显式发 error
        if on_error is not None:
            try:
                on_error(str(exc))
            except Exception:
                logger.exception("on_error callback failed")
        yield stream.emit("error", message=str(exc)).to_sse()
