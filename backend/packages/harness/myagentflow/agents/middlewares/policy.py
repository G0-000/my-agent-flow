"""策略与审批中间件：deny 直接拒绝，ask 没有批准单就挂起。"""
from __future__ import annotations

from typing import Any

from myagentflow.agents.middlewares.chain import Middleware
from myagentflow.sandbox.approvals import ApprovalStore
from myagentflow.sandbox.policy import Decision, evaluate


class PolicyDenied(RuntimeError):
    """危险命令直接拒绝；模型会收到 ERROR，整轮不中断。"""


class ApprovalRequired(RuntimeError):
    """需要人工批准；异常里带 approval_id，供 API 展示。"""

    def __init__(self, approval_id: str, reason: str) -> None:
        super().__init__(f"审批未完成：{approval_id}（{reason}）")
        self.approval_id = approval_id


_SHELL_TOOLS = {"run_command", "start_background_command"}
_MCP_PREFIX = "mcp__"
_MCP_ALLOW_ENV = "MYAF_MCP_ALLOW"


class PolicyMiddleware(Middleware):
    """按 sandbox.policy 判定命令；ask 时校验 approval_id 后放行。"""

    name = "policy"

    def __init__(self, store: ApprovalStore | None = None) -> None:
        self.store = store or ApprovalStore()

    def _gate(self, request: Any, handler: Any, reason: str) -> Any:
        """ask 分支：有匹配的批准单就放行，否则挂起并抛 ApprovalRequired。"""
        tool = getattr(request, "name", "")
        args = getattr(request, "args", {}) or {}
        approval_id = str((getattr(request, "metadata", {}) or {}).get("approval_id") or "")
        if approval_id and self.store.is_approved(approval_id, tool, args):
            return handler(request)
        pending = self.store.find_pending(
            str(getattr(request, "run_id", "") or ""), tool, args
        )
        ap = pending or self.store.create(
            str(getattr(request, "run_id", "") or ""), tool, args
        )
        raise ApprovalRequired(ap.id, reason)

    def wrap_tool_call(self, request: Any, handler: Any) -> Any:
        tool = getattr(request, "name", "")
        args = getattr(request, "args", {}) or {}

        # 外部 MCP 工具默认不可信：未显式 allow 的写操作必须先审批。
        if tool.startswith(_MCP_PREFIX):
            import os

            allowed = {
                x.strip()
                for x in os.getenv(_MCP_ALLOW_ENV, "").split(",")
                if x.strip()
            }
            if tool in allowed:
                return handler(request)
            return self._gate(request, handler, "外部 MCP 工具默认需要审批")

        if tool not in _SHELL_TOOLS:
            return handler(request)

        command = str(args.get("command") or "")
        result = evaluate(command)
        if result.decision is Decision.deny:
            raise PolicyDenied(f"拒绝执行：{result.reason}")

        if result.decision is Decision.ask:
            return self._gate(request, handler, result.reason)

        return handler(request)
