"""离线许可：签名内容 + 功能位。

为什么许可要签名：许可文件会被用户改，
不签名的 JSON 等于把「企业版」写在明文里等别人改。
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time


def _sign(payload: str, key: str) -> str:
    return base64.urlsafe_b64encode(
        hmac.new(key.encode(), payload.encode(), hashlib.sha256).digest()
    ).decode().rstrip("=")


def issue(features: list[str], days: int, key: str) -> str:
    payload = base64.urlsafe_b64encode(
        json.dumps({"features": features, "expires": time.time() + days * 86400}).encode()
    ).decode().rstrip("=")
    return f"{payload}.{_sign(payload, key)}"


def parse(lic: str, key: str, now: float | None = None) -> dict:
    try:
        payload, sig = lic.split(".")
    except ValueError as exc:
        raise ValueError("许可格式不合法") from exc
    if not hmac.compare_digest(_sign(payload, key), sig):
        raise ValueError("许可签名不匹配")
    data = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
    if (now or time.time()) > data["expires"]:
        raise ValueError("许可已过期")
    return data


def has_feature(lic: str, key: str, feature: str, now: float | None = None) -> bool:
    try:
        return feature in parse(lic, key, now).get("features", [])
    except ValueError:
        return False          # 许可不可信：一律当没有
