"""流程（Workflow）：一组有序步骤 + 一次执行记录。

为什么失败要保留已完成产物：用户修完失败那一步后，
不该从第一步重跑（重跑会重复写文件、重复调外部接口）。
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any


@dataclass
class StepResult:
    name: str
    ok: bool
    output: Any = None
    error: str | None = None


@dataclass
class Workflow:
    name: str
    steps: list[tuple[str, Callable[[], Any]]] = field(default_factory=list)
    history: list[StepResult] = field(default_factory=list)

    def run(self) -> list[StepResult]:
        for name, fn in self.steps:
            try:
                out = fn()
                self.history.append(StepResult(name, True, out))
            except Exception as exc:
                self.history.append(StepResult(name, False, error=str(exc)))
                break                    # 失败即停：后面的步骤依赖前面的结果
        return self.history

    def resume_from(self, index: int) -> list[StepResult]:
        """从第 index 步继续（前面已成功的产物留在 history 里）。"""
        for name, fn in self.steps[index:]:
            try:
                self.history.append(StepResult(name, True, fn()))
            except Exception as exc:
                self.history.append(StepResult(name, False, error=str(exc)))
                break
        return self.history
