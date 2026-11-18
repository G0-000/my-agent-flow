"""一、文件说明
    07/01 计划解析：依赖解析与环检测。

二、覆盖
    test_parse_dep()       `depends:` 被解析成前置步骤 id。
    test_cycle_detected()  依赖成环抛 ValueError。

三、运行
    uv run pytest tests/chapters/test_ch07_01_plan.py -q
"""

from __future__ import annotations

import pytest


def test_parse_dep():
    """`depends:` 被解析成前置步骤 id。"""
    from myagentflow.plans.parser import parse

    steps = parse("- [ ] 读代码\n- [ ] 写实现 depends: 读代码")
    assert steps[1].depends == [steps[0].id]


def test_cycle_detected():
    """依赖成环抛 ValueError。"""
    from myagentflow.plans.parser import parse

    with pytest.raises(ValueError):
        parse("- [ ] A depends: B\n- [ ] B depends: A")
