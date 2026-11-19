"""一、文件说明
    02/04 分享：ok / missing / revoked / expired 四种状态。

二、覆盖
    test_share_ok_and_missing()   有效 token 能解析到线程；乱码 token 是 missing。
    test_share_revoked()          撤销后旧 token 立即变成 revoked。
    test_share_expired()          ttl 到期后变成 expired，且不依赖撤销。

三、运行
    uv run pytest tests/chapters/test_ch02_04_shares.py -q
"""

from __future__ import annotations


def test_share_ok_and_missing(tmp_path):
    """有效 token 能解析到线程；乱码 token 是 missing。"""
    from myagentflow.collab.shares import ShareStore

    store = ShareStore(tmp_path / "s.sqlite")
    token = store.create("t1", ttl_seconds=60)
    result = store.resolve(token)
    assert result.status == "ok"
    assert result.thread_id == "t1"
    assert store.resolve("bogus").status == "missing"


def test_share_revoked(tmp_path):
    """撤销后旧 token 立即变成 revoked。"""
    from myagentflow.collab.shares import ShareStore

    store = ShareStore(tmp_path / "s.sqlite")
    token = store.create("t1", ttl_seconds=60)
    store.revoke(token)
    assert store.resolve(token).status == "revoked"


def test_share_expired(tmp_path):
    """ttl 到期后变成 expired：时间戳比较，不靠定时任务。"""
    from myagentflow.collab.shares import ShareStore

    store = ShareStore(tmp_path / "s.sqlite")
    token = store.create("t1", ttl_seconds=50)
    expires_at = store._conn.execute(
        "SELECT expires_at FROM shares WHERE thread_id = ?", ("t1",)
    ).fetchone()[0]
    # 把「现在」推到过期之后一秒；没有撤销，状态必须自己走到 expired
    assert store.resolve(token, now=expires_at + 1).status == "expired"
