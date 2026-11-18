"""一、文件说明
    通知投递：多渠道 + 去重 + 失败隔离。
    为什么失败要隔离：一个 webhook 挂了不该让桌面通知也发不出去。

二、目录结构
    packages/harness/myagentflow/automation/
    ├── __init__.py
    ├── heartbeat.py  心跳：状态没变就别叫模型。
    ├── notify.py  ← 本文件
    ├── scheduler.py  调度器：最小 cron + 重启补偿。
    └── store.py  自动化：规则 + 执行历史。

三、关键方法
    Notifier  按渠道发通知；同一 dedup_key 只发一次。
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field


@dataclass
class Notifier:
    """按渠道发通知；同一 dedup_key 只发一次。"""
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
