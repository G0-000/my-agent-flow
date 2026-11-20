"""一、文件说明
    记忆命名空间 id：user / agent / workspace / person。
    为什么要有命名空间：记忆进入 prompt 前必须知道「属于谁」，否则 A 用户的偏好
    会污染 B 用户；解析函数同时负责把非法/空 id 归一。

二、目录结构
    packages/harness/myagentflow/memory/
    ├── __init__.py
    ├── namespaces.py  ← 本文件
    ├── store.py       原子表读写
    ├── facade.py      remember / recall / forget
    └── recall_snapshot.py

三、关键方法
    user_ns()       用户命名空间，空值归 default。
    agent_ns()      Agent 命名空间，空值退回 user:default。
    workspace_ns()  工作区命名空间，空值抛 ValueError。
    person_ns()     人格命名空间，空值抛 ValueError。
    parse_namespace() 把 "kind:owner" 拆成 (kind, owner)。
"""

from __future__ import annotations


def user_ns(user_id: str = "default") -> str:
    return f"user:{(user_id or 'default').strip() or 'default'}"


def agent_ns(agent_code: str | None) -> str:
    code = (agent_code or "").strip()
    if not code:
        return user_ns("default")
    return f"agent:{code}"


def workspace_ns(workspace_key: str) -> str:
    key = (workspace_key or "").strip()
    if not key:
        raise ValueError("workspace_key required")
    # Accept raw path hash keys like ws-xxx or full workspace id.
    if key.startswith("workspace:"):
        return key
    return f"workspace:{key}"


def person_ns(agent_code: str) -> str:
    code = (agent_code or "").strip().lower()
    if not code:
        raise ValueError("agent_code required")
    return f"person:{code}"


def parse_namespace(ns_id: str) -> tuple[str, str]:
    raw = (ns_id or "").strip()
    if ":" not in raw:
        return "user", raw or "default"
    kind, _, owner = raw.partition(":")
    return kind.strip(), owner.strip()
