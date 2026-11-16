"""流式事件：统一形状 + SSE 序列化。

为什么事件要带 seq：前端断线重连时用 Last-Event-ID 续传，
没有 seq 就只能整段重放，用户会看到重复内容。
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from itertools import count
from typing import Any


@dataclass
class StreamEvent:
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
