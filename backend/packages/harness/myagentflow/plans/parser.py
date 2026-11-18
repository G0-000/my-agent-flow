"""一、文件说明
    计划解析：Markdown → 步骤 DAG。
    为什么建图时就查环：跑到一半发现互相等待，前面的步骤全白做。

二、目录结构
    packages/harness/myagentflow/plans/
    ├── __init__.py
    ├── parser.py  ← 本文件
    ├── router.py  探索预算：给「再试一次」一个硬上限。
    └── workflow.py  流程（Workflow）：一组有序步骤 + 一次执行记录。

三、关键方法
    Step            计划中的一步：标题与依赖的前置步骤 id。
    parse()         把 Markdown 勾选列表解析成 Step 列表，识别 depends。
    check_cycles()  依赖写的是标题时，先映射成 id 再查环。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

# 计划条目：Markdown 任务列表的一行，「[ ] / [x]」都算一个步骤
_STEP = re.compile(r"^\s*-\s*\[[ xX]\]\s*(.+)$")
# 依赖声明：同一步骤行尾写「depends: a, b」，只允许字母数字与逗号
_DEP = re.compile(r"depends:\s*([\w\-, ]+)")


@dataclass
class Step:
    """计划中的一步：标题与依赖的前置步骤 id。"""
    id: str
    title: str
    depends: list[str] = field(default_factory=list)


def parse(markdown: str) -> list[Step]:
    """把 Markdown 勾选列表解析成 Step 列表，识别 depends。"""
    steps: list[Step] = []
    for line in markdown.splitlines():
        m = _STEP.match(line)
        if not m:
            continue
        title = m.group(1).strip()
        dep = _DEP.search(title)
        deps = [d.strip() for d in dep.group(1).split(",")] if dep else []
        sid = f"s{len(steps) + 1}"
        steps.append(Step(id=sid, title=_DEP.sub("", title).strip(), depends=deps))
    check_cycles(steps, by_title=True)
    return steps


def check_cycles(steps: list[Step], by_title: bool = False) -> None:
    """依赖写的是标题时，先映射成 id 再查环。"""
    if by_title:
        index = {s.title: s.id for s in steps}
        for s in steps:
            s.depends = [index.get(d, d) for d in s.depends]
    graph = {s.id: s.depends for s in steps}
    state: dict[str, int] = {}

    def visit(node: str) -> None:
        if state.get(node) == 1:
            raise ValueError(f"计划存在环：{node}")
        if state.get(node) == 2:
            return
        state[node] = 1
        for dep in graph.get(node, []):
            visit(dep)
        state[node] = 2

    for node in graph:
        visit(node)
