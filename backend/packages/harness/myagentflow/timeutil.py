"""一、文件说明
    统一时间戳：落库、快照、记忆版本都用同一个时区与格式。
    为什么叫 utc_now_iso_z 却返回 +08:00：历史调用方依赖这个名字，
    但实际写入的是北京时间；改名会破坏既有数据读取，所以保留名字并写清。

二、目录结构
    packages/harness/myagentflow/
    ├── timeutil.py  ← 本文件
    ├── config/
    └── memory/

三、关键方法
    beijing_now_iso()  当前北京时间 ISO-8601（微秒）。
    utc_now_iso_z()    兼容旧名字的北京时间时间戳。
"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

BEIJING_TZ = ZoneInfo("Asia/Shanghai")


def beijing_now_iso() -> str:
    """当前北京时间 ISO-8601（微秒）。"""
    return datetime.now(BEIJING_TZ).isoformat(timespec="microseconds")


def utc_now_iso_z() -> str:
    """兼容旧名字的北京时间时间戳；不要按名字误以为是 UTC。"""
    return beijing_now_iso()
