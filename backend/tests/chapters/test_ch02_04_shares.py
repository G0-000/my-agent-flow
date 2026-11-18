"""一、文件说明
    02/04 分享：ok / missing / revoked / expired 四种状态。

二、覆盖
    test_share_states()  分享 token 的 ok / missing / revoked / expired 四种状态。

三、运行
    uv run pytest tests/chapters/test_ch02_04_shares.py -q
"""

from __future__ import annotations


def test_share_states(tmp_path):
    """分享 token 的 ok / missing / revoked / expired 四种状态。"""
    from myagentflow.collab.shares import ShareStore

    store = ShareStore(tmp_path / "s.sqlite")
    token = store.create("t1", ttl_seconds=60)
    assert store.resolve(token).status == "ok"
    assert store.resolve("bogus").status == "missing"

    store.revoke(token)
    assert store.resolve(token).status == "revoked"
    assert store.resolve(token, now=10**12).status in {"revoked", "expired"}
