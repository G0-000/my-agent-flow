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


class PolicyMiddleware(Middleware):
    """按 sandbox.policy 判定命令；ask 时校验 approval_id 后放行。"""

    name = "policy"

    def __init__(self, store: ApprovalStore | None = None) -> None:
        self.store = store or ApprovalStore()

    def wrap_tool_call(self, request: Any, handler: Any) -> Any:
        tool = getattr(request, "name", "")
        args = getattr(request, "args", {}) or {}
        if tool not in _SHELL_TOOLS:
            return handler(request)

        command = str(args.get("command") or "")
        result = evaluate(command)
        if result.decision is Decision.deny:
            raise PolicyDenied(f"拒绝执行：{result.reason}")

        if result.decision is Decision.ask:
            approval_id = str((getattr(request, "metadata", {}) or {}).get("approval_id") or "")
            if approval_id and self.store.is_approved(approval_id, tool, args):
                return handler(request)
            pending = self.store.find_pending(
                str(getattr(request, "run_id", "") or ""), tool, args
            )
            ap = pending or self.store.create(
                str(getattr(request, "run_id", "") or ""), tool, args
            )
            raise ApprovalRequired(ap.id, result.reason)

        return handler(request)
