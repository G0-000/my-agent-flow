"""一、文件说明
    子代理注册表：谁能干什么，谁来干。
    为什么要 tags 而不是让模型自由挑：
    子代理名字对模型没有语义，标签才有；而且挑错人的代价是一整轮白跑。

二、目录结构
    packages/harness/myagentflow/subagents/
    ├── __init__.py
    ├── adapter.py  外部 Agent 适配：把 A2A 响应变成内部子代理结果。
    ├── registry.py  ← 本文件
    └── summarize.py  子代理结果汇总：只回填「结论 + 证据 + 失败原因」。

三、关键方法
    SubagentSpec      子代理声明：名字、描述、标签、执行函数。
    SubagentRegistry  按名字注册与查找子代理。
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class SubagentSpec:
    """子代理声明：名字、描述、标签、执行函数。"""
    name: str
    description: str
    tags: tuple[str, ...]
    run: Callable[..., Any]


class SubagentRegistry:
    """按名字注册与查找子代理。"""
    def __init__(self) -> None:
        self._agents: dict[str, SubagentSpec] = {}

    def register(self, spec: SubagentSpec) -> None:
        self._agents[spec.name] = spec

    def pick(self, wanted_tags: list[str]) -> SubagentSpec | None:
        """标签命中越多越优先；同分取注册更早的（稳定）。"""
        scored = [
            (len(set(wanted_tags) & set(s.tags)), i, s)
            for i, s in enumerate(self._agents.values())
        ]
        best = max(scored, key=lambda x: (x[0], -x[1]), default=None)
        if best is None or best[0] == 0:
            return None
        return best[2]

    def describe(self) -> str:
        return "\n".join(f"- {s.name}：{s.description}（{'/'.join(s.tags)}）"
                         for s in self._agents.values())
