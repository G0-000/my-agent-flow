"""桥接鉴权：浏览器桥 / CUA 桥共用的 token 校验。

为什么不用 ==：字符串比较会在第一个不同字符处提前返回，
攻击者能靠响应时间逐位猜出 token。
"""
from __future__ import annotations

import hmac
import os

BRIDGE_TOKEN_ENV = "MYAF_BRIDGE_TOKEN"


def verify_bridge_token(provided: str | None) -> bool:
    expected = os.getenv(BRIDGE_TOKEN_ENV, "")
    if not expected or not provided:
        return False          # 没配 token 一律拒绝，不能「没配就放行」
    return hmac.compare_digest(provided, expected)
