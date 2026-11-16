"""通知投递：多渠道 + 去重 + 失败隔离。

为什么失败要隔离：一个 webhook 挂了不该让桌面通知也发不出去。
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field


@dataclass
class Notifier:
    senders: dict[str, Callable[[str], bool]] = field(default_factory=dict)
    _sent: set[str] = field(default_factory=set)

    def send(self, channel: str, text: str, dedup_key: str | None = None) -> dict[str, str]:
        """返回每个渠道的结果：sent / skipped / failed。"""
        results: dict[str, str] = {}
        key = dedup_key or text
        for name, fn in self.senders.items():
            if channel not in {"all", name}:
                continue
            if f"{name}:{key}" in self._sent:
                results[name] = "skipped"
                continue
            try:
                ok = fn(text)
                results[name] = "sent" if ok else "failed"
                if ok:
                    self._sent.add(f"{name}:{key}")
            except Exception:
                results[name] = "failed"      # 单渠道异常不影响别的渠道
        return results
