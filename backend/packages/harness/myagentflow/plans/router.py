"""一、文件说明
    探索预算：给「再试一次」一个硬上限。
    为什么必须硬上限：模型天然倾向再试一次，没有外部约束时，
    一个死循环能烧掉整晚的额度和上下文。

二、目录结构
    packages/harness/myagentflow/plans/
    ├── __init__.py
    ├── parser.py  计划解析：Markdown → 步骤 DAG。
    ├── router.py  ← 本文件
    └── workflow.py  流程（Workflow）：一组有序步骤 + 一次执行记录。

三、关键方法
    Strategy
    Budget
    choose()
    spend()
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Strategy(str, Enum):
    exhaustive = "exhaustive"    # 预算充足：可以枚举
    heuristic = "heuristic"      # 预算一般：只走最可能的路径
    stop = "stop"                # 预算耗尽：停手并汇报


@dataclass(frozen=True)
class Budget:
    max_steps: int = 20
    max_seconds: int = 600
    steps_used: int = 0
    seconds_used: int = 0


def choose(b: Budget) -> Strategy:
    step_ratio = 1 - b.steps_used / max(1, b.max_steps)
    time_ratio = 1 - b.seconds_used / max(1, b.max_seconds)
    remaining = min(step_ratio, time_ratio)
    if remaining <= 0:
        return Strategy.stop
    if remaining < 0.3:
        return Strategy.heuristic
    return Strategy.exhaustive


def spend(b: Budget, steps: int = 1, seconds: int = 0) -> Budget:
    return Budget(b.max_steps, b.max_seconds, b.steps_used + steps, b.seconds_used + seconds)
