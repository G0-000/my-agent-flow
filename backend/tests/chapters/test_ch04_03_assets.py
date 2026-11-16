from __future__ import annotations

import pytest


def test_assets(tmp_path):
    from myagentflow.memory.assets import Asset, AssetStore

    s = AssetStore(tmp_path / "a.sqlite")
    s.add(Asset("t1", "todo", "写测试"))
    s.add(Asset("t1", "artifact", "报告", "/tmp/x.md"))
    assert [a["kind"] for a in s.list("t1")] == ["artifact", "todo"]
    assert [a["title"] for a in s.list("t1", kind="todo")] == ["写测试"]

    with pytest.raises(ValueError):
        s.add(Asset("t1", "unknown", "x"))
