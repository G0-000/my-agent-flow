"""一、文件说明
    审计中间件：每次工具调用留一行。记工具名、参数摘要、耗时、成功/失败。
    为什么只留一行：审计日志是排查用的，不是全量转录；完整参数可能带密钥/大文本。

二、目录结构
    packages/harness/myagentflow/agents/middlewares/
    ├── __init__.py
    ├── audit.py  ← 本文件
    └── chain.py  中间件链：洋葱包裹，第一个在最外层

三、关键方法
    _brief()         把工具参数压成一行短文本并截断，供审计日志用。
    AuditMiddleware  记录每次工具调用的参数、耗时与结果的中间件。
"""
from __future__ import annotations

import json
import logging
import time
from typing import Any

from myagentflow.agents.middlewares.chain import Middleware

logger = logging.getLogger("myaf.audit")


def _brief(args: dict[str, Any], limit: int = 120) -> str:
    """把工具参数压成一行短文本并截断，供审计日志用。"""
    text = json.dumps(args, ensure_ascii=False, default=str)
    return text if len(text) <= limit else text[:limit] + "…"   # 截断：日志里不该出现完整密钥


def _tool_name(request: Any) -> str:
    """从 ToolCallRequest 里取工具名；结构不对时给 unknown_tool。"""
    tool_call = getattr(request, "tool_call", None)
    if isinstance(tool_call, dict):
        return str(tool_call.get("name") or "unknown_tool")
    return "unknown_tool"


def _tool_args(request: Any) -> dict[str, Any]:
    """从 ToolCallRequest 里取参数；非 dict 一律当空参数。"""
    tool_call = getattr(request, "tool_call", None)
    if isinstance(tool_call, dict):
        args = tool_call.get("args") or {}
        return args if isinstance(args, dict) else {}
    return {}


class AuditMiddleware(Middleware):
    """记录每次工具调用的参数、耗时与结果的中间件。"""
    name = "audit"

    def wrap_tool_call(self, request: Any, handler: Any) -> Any:
        name = _tool_name(request)
        args = _tool_args(request)
        t0 = time.perf_counter()
        try:
            result = handler(request)
        except Exception as exc:
            # 失败也要留痕，但异常必须继续抛：审计层不负责吞错
            cost = time.perf_counter() - t0
            logger.info(
                "tool=%s args=%s cost=%.3fs ok=False error=%s",
                name, _brief(args), cost, exc.__class__.__name__,
            )
            raise
        cost = time.perf_counter() - t0
        logger.info("tool=%s args=%s cost=%.3fs ok=True", name, _brief(args), cost)
        return result
