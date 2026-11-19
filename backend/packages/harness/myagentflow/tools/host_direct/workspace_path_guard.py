"""一、文件说明
    宿主路径守卫：解析 + 可切换策略。
    为什么要有显式开关：很多宿主工具默认「信任调用方」，一旦上层把用户输入
    直接透传，路径就会逃出工作区；这里把策略摆到明面上，便于逐章收紧。

二、目录结构
    packages/harness/myagentflow/tools/host_direct/
    ├── __init__.py
    ├── background_bash.py  后台命令：启动、查询、终止。
    ├── bridge_auth.py  桥接鉴权：浏览器桥 / CUA 桥共用的 token 校验。
    └── workspace_path_guard.py  ← 本文件

三、关键方法
    Policy      路径策略：disabled 原样放行，confine 限制在工作区内。
    Resolution  路径解析结果：实际路径、是否在区内、结论。
    resolve()   相对路径先拼 workspace，再 realpath 折平 .. 与软链，按策略给出结论。
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from enum import Enum
from pathlib import Path


class Policy(str, Enum):
    """路径策略：disabled 原样放行，confine 限制在工作区内。"""
    disabled = "disabled"   # 原样使用，绝对路径也放行（默认策略）
    confine = "confine"     # 必须落在 workspace 之下


@dataclass(frozen=True)
class Resolution:
    """路径解析结果：实际路径、是否在区内、结论。"""
    path: Path
    inside: bool
    decision: str          # allowed | escaped | resolved


def resolve(path: str, workspace: str | Path, policy: Policy = Policy.disabled) -> Resolution:
    """相对路径先拼 workspace，再 realpath 折平 .. 与软链，按策略给出结论。

    相对路径必须以 workspace 为基准：否则进程 cwd 不同，同一输入会落到不同文件，
    confine 的判断也跟着漂移。
    """
    root = Path(os.path.realpath(str(workspace)))
    candidate = Path(os.path.expanduser(path))
    if not candidate.is_absolute():
        candidate = root / candidate
    # realpath 先把 `..`、软链、重复分隔符全部折平，再做前缀比较
    target = Path(os.path.realpath(str(candidate)))
    inside = target == root or root in target.parents
    if policy is Policy.disabled:
        return Resolution(target, inside, "allowed")
    return Resolution(target, inside, "resolved" if inside else "escaped")
