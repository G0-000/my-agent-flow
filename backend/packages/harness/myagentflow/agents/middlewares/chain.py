"""一、文件说明
    中间件链：进正序、出逆序。
    为什么 after 要逆序：它是「清理」语义——后申请的资源先释放，
    否则 A 依赖 B 的资源时，A 先清理会让 B 拿到已失效的对象。

二、目录结构
    packages/harness/myagentflow/agents/middlewares/
    ├── __init__.py
    ├── audit.py  审计中间件：每次工具调用留一行。
    └── chain.py  ← 本文件

三、关键方法
    Middleware
    run_chain()
"""
from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any


class Middleware:
    name: str = "middleware"

    def before_tool(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        return args              # 默认不改参数

    def after_tool(self, name: str, args: dict[str, Any], result: Any) -> Any:
        return result            # 默认不改结果


def run_chain(mws: Iterable[Middleware], name: str, args: dict[str, Any],
              call: Callable[[str, dict[str, Any]], Any]) -> Any:
    entered: list[Middleware] = []
    current = args
    try:
        for mw in mws:
            current = mw.before_tool(name, current)
            entered.append(mw)
        result = call(name, current)
    finally:
        for mw in reversed(entered):     # 逆序收尾
            result = mw.after_tool(name, current, locals().get("result"))
    return result
