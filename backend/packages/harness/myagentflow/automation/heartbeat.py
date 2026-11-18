"""一、文件说明
    心跳：状态没变就别叫模型。
    为什么用指纹而不是时间：
    按时间触发的话，一切正常时也在烧 token；
    按指纹触发，只有「真的有变化」才动作。

二、目录结构
    packages/harness/myagentflow/automation/
    ├── __init__.py
    ├── heartbeat.py  ← 本文件
    ├── notify.py  通知投递：多渠道 + 去重 + 失败隔离。
    ├── scheduler.py  调度器：最小 cron + 重启补偿。
    └── store.py  自动化：规则 + 执行历史。

三、关键方法
    fingerprint()  把状态字典排序后哈希成 16 位指纹，用于判断状态有没有变。
    Heartbeat      心跳节流：状态没变不重复跑，每小时最多 max_per_hour 次。
"""
from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field


def fingerprint(values: dict[str, str]) -> str:
    """把状态字典排序后哈希成 16 位指纹，用于判断状态有没有变。"""
    raw = "|".join(f"{k}={values[k]}" for k in sorted(values))
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


@dataclass
class Heartbeat:
    """心跳节流：状态没变不重复跑，每小时最多 max_per_hour 次。"""
    max_per_hour: int = 6
    _last_fp: str | None = None
    _events: list[float] = field(default_factory=list)

    def should_run(self, state: dict[str, str], now: float | None = None) -> bool:
        now = now or time.time()
        fp = fingerprint(state)
        if fp == self._last_fp:
            return False                     # 没变化：省一次模型调用
        self._events = [t for t in self._events if now - t < 3600]
        if len(self._events) >= self.max_per_hour:
            return False                     # 变化太频繁：节流
        self._last_fp = fp
        self._events.append(now)
        return True
