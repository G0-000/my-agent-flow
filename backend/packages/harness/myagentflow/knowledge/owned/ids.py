"""一、文件说明
    id 与时间工具：知识库里的文档、块、文件夹、图节点都用同一套前缀 id。
    为什么不用自增整数：上传/重建会并发生成 id，字符串前缀便于日志直接看出对象类型。

二、目录结构
    packages/harness/myagentflow/knowledge/owned/
    ├── __init__.py
    ├── db.py  连接与锁
    ├── ids.py  ← 本文件
    ├── schema.py  表结构
    ├── service.py  知识库、文档、目录与块
    └── kg.py  实体图节点与边

三、关键方法
    new_id()  生成带前缀的 uuid hex。
    utc_now() 生成 UTC 秒级 ISO 时间。
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime


def new_id(prefix: str = "") -> str:
    """生成 ``prefix + uuid hex``；prefix 为空时只返回 hex。"""
    uid = uuid.uuid4().hex
    return f"{prefix}{uid}" if prefix else uid


def utc_now() -> str:
    """当前 UTC 时间，秒级精度，以 Z 结尾。"""
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
