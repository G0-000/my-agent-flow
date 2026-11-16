from __future__ import annotations

import pytest


def test_parse_dep():
    from myagentflow.plans.parser import parse

    steps = parse("- [ ] 读代码\n- [ ] 写实现 depends: 读代码")
    assert steps[1].depends == [steps[0].id]


def test_cycle_detected():
    from myagentflow.plans.parser import parse

    with pytest.raises(ValueError):
        parse("- [ ] A depends: B\n- [ ] B depends: A")
