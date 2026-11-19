"""一、文件说明
    流式事件：统一形状 + SSE 序列化。
    为什么事件要带 seq：前端按 seq 排序、去重；服务端重放（Last-Event-ID 续传）不在本章，
    那需要 run 状态与事件缓冲，先把事件形状固定下来。

二、目录结构
    packages/harness/myagentflow/runtime/
    ├── __init__.py
    ├── events.py  ← 本文件
    └── streaming.py  把 LangGraph 的 astream_events 收敛成我们自己的事件。

三、关键方法
    StreamEvent  一条流事件：类型、数据、序号，可转成 SSE 帧。
    EventStream  把「生成事件」和「排 seq」分开，调用方只管产出业务数据。
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from itertools import count
from typing import Any


@dataclass
class StreamEvent:
    """一条流事件：类型、数据、序号，可转成 SSE 帧。"""
    type: str                      # token | tool | done | error
    data: dict[str, Any] = field(default_factory=dict)
    seq: int = 0

    def to_sse(self) -> str:
        payload = json.dumps({**self.data, "seq": self.seq}, ensure_ascii=False)
        return f"id: {self.seq}\nevent: {self.type}\ndata: {payload}\n\n"


class EventStream:
    """把「生成事件」和「排 seq」分开，调用方只管产出业务数据。"""

    def __init__(self) -> None:
        self._counter = count(1)

    def emit(self, type_: str, **data: Any) -> StreamEvent:
        return StreamEvent(type=type_, data=data, seq=next(self._counter))
