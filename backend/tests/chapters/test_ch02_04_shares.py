from __future__ import annotations


def test_share_states(tmp_path):
    from myagentflow.collab.shares import ShareStore

    store = ShareStore(tmp_path / "s.sqlite")
    token = store.create("t1", ttl_seconds=60)
    assert store.resolve(token).status == "ok"
    assert store.resolve("bogus").status == "missing"

    store.revoke(token)
    assert store.resolve(token).status == "revoked"
    assert store.resolve(token, now=10**12).status in {"revoked", "expired"}
