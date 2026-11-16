from __future__ import annotations


def test_acl():
    from myagentflow.authz.acl import Resource, can

    r = Resource("workspace", "w1", "alice")
    assert can("alice", {}, r, "delete") is True
    assert can("bob", {"bob": "viewer"}, r, "write") is False
    assert can("bob", {"bob": "member"}, r, "write") is True
    assert can("carol", {}, r, "read") is False
