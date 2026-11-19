"""一、文件说明
    工具调用中间件链：洋葱式包裹，列表第一个在最外层。
    为什么不用「before 列表 + after 列表」：EvoFlow 的中间件统一实现
    `wrap_tool_call(request, handler)`，进入顺序与退出顺序由嵌套自然保证，
    不会出现「after 忘了逆序」这种低级错误。

二、目录结构
    packages/harness/myagentflow/agents/middlewares/
    ├── __init__.py
    ├── audit.py  工具审计：工具名、参数摘要、耗时、成功/失败
    └── chain.py  ← 本文件：中间件基类与链组装

三、关键方法
    Middleware            中间件基类：默认直接放行，子类覆盖 wrap_tool_call。
    run_chain()           把中间件按列表顺序包成洋葱，执行最外层。
"""
from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any


class Middleware:
    """中间件基类：默认直接放行，子类覆盖 wrap_tool_call。"""
    name: str = "middleware"

    def wrap_tool_call(
        self,
        request: Any,
        handler: Callable[[Any], Any],
    ) -> Any:
        """包住一次工具调用；默认不改请求，直接交给下一层。"""
        return handler(request)


def run_chain(
    middlewares: Iterable[Middleware],
    request: Any,
    call: Callable[[Any], Any],
) -> Any:
    """把中间件按列表顺序包成洋葱，执行最外层。

    列表 [m0, m1, m2] 的执行顺序：
        m0 进入 → m1 进入 → m2 进入 → 真正工具 → m2 退出 → m1 退出 → m0 退出

    第一个中间件在最外层：它能最早改写请求、最晚看到结果（典型审计/计时）。
    """
    handler = call
    for mw in reversed(list(middlewares)):
        # 默认参数绑定：不绑的话闭包会共享最后一个 handler
        handler = _wrap_one(mw, handler)
    return handler(request)


def _wrap_one(mw: Middleware, inner: Callable[[Any], Any]) -> Callable[[Any], Any]:
    """把单个中间件包在 inner 外面；抽出来是为了避免闭包捕获错层。"""
    def wrapped(request: Any) -> Any:
        return mw.wrap_tool_call(request, inner)

    return wrapped
