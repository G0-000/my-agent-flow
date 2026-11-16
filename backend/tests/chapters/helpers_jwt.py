"""测试用 HS256 token 生成器（只服务测试，不参与运行时）。"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time

SECRET = "k"          # 与测试里 verify(..., "k", ...) 保持一致


def _b64(obj: dict) -> str:
    raw = json.dumps(obj, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")   # JWT 用无填充 base64


def make_token(sub: str = "u1", exp_offset: float = 60,
               aud: str = "myaf", iss: str = "myaf",
               secret: str = SECRET) -> str:
    """exp_offset 是相对现在的秒数：正数=未来过期，负数=已过期。"""
    header = _b64({"alg": "HS256", "typ": "JWT"})
    body = _b64({"sub": sub, "aud": aud, "iss": iss, "exp": time.time() + exp_offset})
    sig = base64.urlsafe_b64encode(
        hmac.new(secret.encode(), f"{header}.{body}".encode(), hashlib.sha256).digest()
    ).decode().rstrip("=")
    return f"{header}.{body}.{sig}"
