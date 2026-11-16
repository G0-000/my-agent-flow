"""Trace：一次运行的耗时与成本。

为什么不用 print 调试：线上没有 stdout，
trace 必须能以结构化字段落到日志/表里，才能按 run_id 追。
"""
from __future__ import annotations

import json
import time
from contextlib import contextmanager
from dataclasses import dataclass, field


@dataclass
class Span:
    name: str
    start: float = field(default_factory=time.time)
    end: float | None = None
    meta: dict = field(default_factory=dict)

    @property
    def ms(self) -> float:
        return ((self.end or time.time()) - self.start) * 1000


@dataclass
class Trace:
    run_id: str
    spans: list[Span] = field(default_factory=list)
    tokens: int = 0

    @contextmanager
    def span(self, name: str, **meta):
        s = Span(name=name, meta=meta)
        try:
            yield s
        finally:
            s.end = time.time()
            self.spans.append(s)

    def add_tokens(self, n: int) -> None:
        self.tokens += n

    def dump(self) -> str:
        return json.dumps({
            "run_id": self.run_id,
            "tokens": self.tokens,
            "spans": [{"name": s.name, "ms": round(s.ms, 1), **s.meta} for s in self.spans],
        }, ensure_ascii=False)
