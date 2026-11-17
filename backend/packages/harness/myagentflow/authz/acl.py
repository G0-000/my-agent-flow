"""ACL：角色 → 权限 → 资源。

为什么 owner 单独判：把 owner 也塞进角色表，
会出现「管理员改了策略把自己锁在门外」。
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
    kind: str
    id: str
    owner: str


def can(principal: str, roles: dict[str, str], resource: Resource, action: str) -> bool:
    if resource.owner == principal:
        return True                      # owner 永远有权
    role = roles.get(principal, "")
    return action in ROLES.get(role, set())
