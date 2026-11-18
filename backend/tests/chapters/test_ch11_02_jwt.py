"""一、文件说明
    11/02 JWT：验签、篡改与过期。

二、覆盖
    test_tamper_detected()  正常 token 通过；改签名与过期 token 都抛 ValueError。

三、运行
    uv run pytest tests/chapters/test_ch11_02_jwt.py -q
"""

from __future__ import annotations

import pytest


def test_tamper_detected():
    """正常 token 通过；改签名与过期 token 都抛 ValueError。"""
    from myagentflow.authz.jwt import verify

    from tests.chapters.helpers_jwt import make_token

    good = make_token(sub="u1", exp_offset=60)
    claims = verify(good, "k", "myaf", "myaf")
    assert claims["sub"] == "u1"

    bad = good[:-2] + ("aa" if good[-2:] != "aa" else "bb")
    with pytest.raises(ValueError):
        verify(bad, "k", "myaf", "myaf")

    with pytest.raises(ValueError):
        verify(make_token(sub="u1", exp_offset=-10), "k", "myaf", "myaf")
