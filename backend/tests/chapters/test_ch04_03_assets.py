"""一、文件说明
    04/03 资产：按线程/类型查询，非法类型拒收。

二、覆盖
    test_assets()  资产按时间列出、按 kind 过滤，非法 kind 抛 ValueError。

三、运行
    uv run pytest tests/chapters/test_ch04_03_assets.py -q
"""

from __future__ import annotations

import pytest


def test_assets(tmp_path):
    """资产按时间列出、按 kind 过滤，非法 kind 抛 ValueError。"""
    from myagentflow.memory.assets import Asset, AssetStore

    s = AssetStore(tmp_path / "a.sqlite")
    s.add(Asset("t1", "todo", "写测试"))
    s.add(Asset("t1", "artifact", "报告", "/tmp/x.md"))
    assert [a["kind"] for a in s.list("t1")] == ["artifact", "todo"]
    assert [a["title"] for a in s.list("t1", kind="todo")] == ["写测试"]

    with pytest.raises(ValueError):
        s.add(Asset("t1", "unknown", "x"))
