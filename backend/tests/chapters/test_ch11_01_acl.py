"""一、文件说明
    11/01 ACL：属主与角色权限。

二、覆盖
    test_acl()  属主可删；viewer 不能写；member 能写；无角色连读都不行。

三、运行
    uv run pytest tests/chapters/test_ch11_01_acl.py -q
"""

from __future__ import annotations


def test_acl():
    """属主可删；viewer 不能写；member 能写；无角色连读都不行。"""
    from myagentflow.authz.acl import Resource, can

    r = Resource("workspace", "w1", "alice")
    assert can("alice", {}, r, "delete") is True
    assert can("bob", {"bob": "viewer"}, r, "write") is False
    assert can("bob", {"bob": "member"}, r, "write") is True
    assert can("carol", {}, r, "read") is False
