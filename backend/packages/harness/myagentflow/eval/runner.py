"""一、文件说明
    Eval：固定用例 + 可判定的断言。
    为什么不用「让模型打分」：模型评分每次都会飘，
    回归测试需要的是稳定信号，哪怕它很粗糙。

二、目录结构
    packages/harness/myagentflow/eval/
    ├── __init__.py
    └── runner.py  ← 本文件

三、关键方法
    Case     一条评测用例：提示词与回答必须包含的片段。
    score()  回答是否包含用例要求的全部片段。
    run()    跑完全部用例并汇总；单条失败不影响其余用例。
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True)
class Case:
    """一条评测用例：提示词与回答必须包含的片段。"""
    name: str
    prompt: str
    must_contain: tuple[str, ...] = ()


def score(case: Case, answer: str) -> bool:
    """回答是否包含用例要求的全部片段。"""
    return all(k in answer for k in case.must_contain)


def run(cases: list[Case], answer_fn: Callable[[str], str]) -> dict:
    """跑完全部用例并汇总；单条失败不影响其余用例。"""
    results = []
    for c in cases:
        try:
            ok = score(c, answer_fn(c.prompt))
        except Exception as exc:
            results.append({"name": c.name, "ok": False, "error": str(exc)})
            continue
        results.append({"name": c.name, "ok": ok})

    passed = sum(1 for r in results if r["ok"])
    return {"total": len(results), "passed": passed,
            "rate": round(passed / max(1, len(results)), 3), "results": results}
