"""JWT 校验：HS256，手写。

为什么不用现成库：这一步要理解「先验签再读 payload」这件事，
顺序反了等于相信未经验证的内容。
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time


def _b64d(part: str) -> bytes:
    pad = "=" * (-len(part) % 4)
    return base64.urlsafe_b64decode(part + pad)


def verify(token: str, secret: str, audience: str, issuer: str,
           now: float | None = None) -> dict:
    try:
        head_b64, body_b64, sig_b64 = token.split(".")
    except ValueError as exc:
        raise ValueError("token 结构不合法") from exc

    expected = hmac.new(secret.encode(), f"{head_b64}.{body_b64}".encode(), hashlib.sha256).digest()
    if not hmac.compare_digest(_b64d(sig_b64), expected):
        raise ValueError("签名不匹配")

    claims = json.loads(_b64d(body_b64))
    now = now or time.time()
    if claims.get("exp") and now > claims["exp"]:
        raise ValueError("token 已过期")
    if claims.get("aud") != audience:
        raise ValueError("audience 不匹配")
    if claims.get("iss") != issuer:
        raise ValueError("issuer 不匹配")
    return claims
