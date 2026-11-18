"""一、文件说明
    桥接鉴权：浏览器桥 / CUA 桥共用的 token 校验。
    为什么不用 ==：字符串比较会在第一个不同字符处提前返回，
    攻击者能靠响应时间逐位猜出 token。

二、目录结构
    packages/harness/myagentflow/tools/host_direct/
    ├── __init__.py
    ├── background_bash.py  后台命令：启动、查询、终止。
    ├── bridge_auth.py  ← 本文件
    └── workspace_path_guard.py  宿主路径守卫：解析 + 可切换策略。

三、关键方法
    verify_bridge_token()  校验宿主桥接 token；没配 token 一律拒绝，不「没配就放行」。
"""
from __future__ import annotations

import hmac
import os

# token 从环境变量读，不落配置文件：桥接 token 等同于本机执行权限
BRIDGE_TOKEN_ENV = "MYAF_BRIDGE_TOKEN"


def verify_bridge_token(provided: str | None) -> bool:
    """校验宿主桥接 token；没配 token 一律拒绝，不「没配就放行」。"""
    expected = os.getenv(BRIDGE_TOKEN_ENV, "")
    if not expected or not provided:
        return False          # 没配 token 一律拒绝，不能「没配就放行」
    return hmac.compare_digest(provided, expected)
