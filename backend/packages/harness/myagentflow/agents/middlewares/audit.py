"""一、文件说明
    审计中间件：每次工具调用留一行。

二、目录结构
    packages/harness/myagentflow/agents/middlewares/
    ├── __init__.py
    ├── audit.py  ← 本文件
    └── chain.py  中间件链：进正序、出逆序。

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


class AuditMiddleware(Middleware):
    """记录每次工具调用的参数、耗时与结果的中间件。"""
    name = "audit"

    def __init__(self) -> None:
        self._t0: dict[str, float] = {}

    def before_tool(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        self._t0[name] = time.time()
        return args

    def after_tool(self, name: str, args: dict[str, Any], result: Any) -> Any:
        cost = time.time() - self._t0.pop(name, time.time())
        logger.info("tool=%s args=%s cost=%.3fs ok=%s", name, _brief(args), cost,
                    not isinstance(result, Exception))
        return result
