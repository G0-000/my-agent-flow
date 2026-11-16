from __future__ import annotations

import pytest


def test_tamper_detected():
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
