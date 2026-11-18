"""一、文件说明
    调度器：最小 cron + 重启补偿。
    为什么不用 croniter：只支持五段和 `*` 就够本章用，
    自己写反而能讲清「每分钟对齐」这件事；要全语法再引库。

二、目录结构
    packages/harness/myagentflow/automation/
    ├── __init__.py
    ├── heartbeat.py  心跳：状态没变就别叫模型。
    ├── notify.py  通知投递：多渠道 + 去重 + 失败隔离。
    ├── scheduler.py  ← 本文件
    └── store.py  自动化：规则 + 执行历史。

三、关键方法
    _match()   判断 cron 单个字段是否命中某值，支持 *、*/n 与逗号枚举。
    matches()  判断五段 cron 是否命中给定时间戳。
    Scheduler  记录每个自动化的上次运行时间，避免同一时间窗重复触发。
"""
from __future__ import annotations

import time
from dataclasses import dataclass


def _match(field: str, value: int) -> bool:
    """判断 cron 单个字段是否命中某值，支持 *、*/n 与逗号枚举。"""
    if field == "*":
        return True
    for part in field.split(","):
        if part.startswith("*/"):
            step = int(part[2:])
            if step and value % step == 0:
                return True
        elif "-" in part:
            lo, hi = part.split("-")
            if int(lo) <= value <= int(hi):
                return True
        elif value == int(part):
            return True
    return False


def matches(cron: str, ts: float) -> bool:
    """判断五段 cron 是否命中给定时间戳。"""
    minute, hour, day, month, weekday = cron.split()
    t = time.localtime(ts)
    return (
        _match(minute, t.tm_min) and _match(hour, t.tm_hour) and _match(day, t.tm_mday)
        and _match(month, t.tm_mon) and _match(weekday, (t.tm_wday + 1) % 7)
    )


@dataclass
class Scheduler:
    """记录每个自动化的上次运行时间，避免同一时间窗重复触发。"""
    last_run: dict[str, float]

    def due(self, automation_id: str, cron: str, now: float | None = None) -> bool:
        now = now or time.time()
        if not matches(cron, now):
            return False
        # 同一分钟内只触发一次
        return int(now // 60) * 60 != int(self.last_run.get(automation_id, 0) // 60) * 60

    def catch_up(self, automation_id: str, cron: str, now: float | None = None,
                 limit: int = 3) -> int:
        """重启后补跑：从 last_run 到 now 之间命中的分钟数（最多 limit 次）。"""
        now = now or time.time()
        last = self.last_run.get(automation_id, now - 3600)
        count = 0
        ts = last - (last % 60) + 60
        while ts <= now and count < limit:
            if matches(cron, ts):
                count += 1
            ts += 60
        return count
