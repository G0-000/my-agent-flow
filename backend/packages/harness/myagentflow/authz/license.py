"""一、文件说明
    离线许可：签名内容 + 功能位。
    为什么许可要签名：许可文件会被用户改，
    不签名的 JSON 等于把「企业版」写在明文里等别人改。

二、目录结构
    packages/harness/myagentflow/authz/
    ├── __init__.py
    ├── acl.py  ACL：角色 → 权限 → 资源。
    ├── jwt.py  JWT 校验：HS256，手写。
    └── license.py  ← 本文件

三、关键方法
    _sign()        用 HMAC-SHA256 对许可载荷签名，输出 base64url。
    issue()        签发带功能列表与有效期的许可串。
    parse()        校验许可签名并解出 features/expires；签名不符或过期抛 ValueError。
    has_feature()  判断许可是否包含某功能；解析失败一律返回 False。
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time


def _sign(payload: str, key: str) -> str:
    """用 HMAC-SHA256 对许可载荷签名，输出 base64url。"""
    return base64.urlsafe_b64encode(
        hmac.new(key.encode(), payload.encode(), hashlib.sha256).digest()
    ).decode().rstrip("=")


def issue(features: list[str], days: int, key: str) -> str:
    """签发带功能列表与有效期的许可串。"""
    payload = base64.urlsafe_b64encode(
        json.dumps({"features": features, "expires": time.time() + days * 86400}).encode()
    ).decode().rstrip("=")
    return f"{payload}.{_sign(payload, key)}"


def parse(lic: str, key: str, now: float | None = None) -> dict:
    """校验许可签名并解出 features/expires；签名不符或过期抛 ValueError。"""
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
    """判断许可是否包含某功能；解析失败一律返回 False。"""
    try:
        return feature in parse(lic, key, now).get("features", [])
    except ValueError:
        return False          # 许可不可信：一律当没有
