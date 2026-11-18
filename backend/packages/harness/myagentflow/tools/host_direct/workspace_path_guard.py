"""一、文件说明
    宿主路径守卫：解析 + 可切换策略。
    EvoFlow 的实现把 confinement 关掉了（docstring 明写 no confinement），
    这里保留同样行为，但把它变成一个显式开关，避免「以为有护栏」。

二、目录结构
    packages/harness/myagentflow/tools/host_direct/
    ├── __init__.py
    ├── background_bash.py  后台命令：启动、查询、终止。
    ├── bridge_auth.py  桥接鉴权：浏览器桥 / CUA 桥共用的 token 校验。
    └── workspace_path_guard.py  ← 本文件

三、关键方法
    Policy
    Resolution
    resolve()
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from enum import Enum
from pathlib import Path


class Policy(str, Enum):
    disabled = "disabled"   # 原样使用，绝对路径也放行（默认策略）
    confine = "confine"     # 必须落在 workspace 之下


@dataclass(frozen=True)
class Resolution:
    path: Path
    inside: bool
    decision: str          # allowed | escaped | resolved


def resolve(path: str, workspace: str | Path, policy: Policy = Policy.disabled) -> Resolution:
    root = Path(os.path.realpath(str(workspace)))
    # realpath 先把 `..`、软链、重复分隔符全部折平，再做前缀比较
    target = Path(os.path.realpath(os.path.expanduser(path)))
    inside = target == root or root in target.parents
    if policy is Policy.disabled:
        return Resolution(target, inside, "allowed")
    return Resolution(target, inside, "resolved" if inside else "escaped")
