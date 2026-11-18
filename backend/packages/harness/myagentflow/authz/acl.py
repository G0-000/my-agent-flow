"""一、文件说明
    ACL：角色 → 权限 → 资源。
    为什么 owner 单独判：把 owner 也塞进角色表，
    会出现「管理员改了策略把自己锁在门外」。

二、目录结构
    packages/harness/myagentflow/authz/
    ├── __init__.py
    ├── acl.py  ← 本文件
    ├── jwt.py  JWT 校验：HS256，手写。
    └── license.py  离线许可：签名内容 + 功能位。

三、关键方法
    Resource  被访问的资源：类型、id、属主。
    can()     判断某人能否对资源执行动作：属主直接放行，否则查角色权限表。
"""
from __future__ import annotations

from dataclasses import dataclass

# 角色到权限的映射。owner 不在这张表里：owner 走 can() 里的身份判断，
# 否则改策略时容易把 owner 自己锁在门外。
ROLES: dict[str, set[str]] = {
    "owner": {"read", "write", "delete", "share"},
    "member": {"read", "write"},
    "viewer": {"read"},
}


@dataclass(frozen=True)
class Resource:
    """被访问的资源：类型、id、属主。"""
    kind: str
    id: str
    owner: str


def can(principal: str, roles: dict[str, str], resource: Resource, action: str) -> bool:
    """判断某人能否对资源执行动作：属主直接放行，否则查角色权限表。"""
    if resource.owner == principal:
        return True                      # owner 永远有权
    role = roles.get(principal, "")
    return action in ROLES.get(role, set())
