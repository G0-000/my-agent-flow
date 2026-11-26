"""第 03.7 章：策略与审批中间件的最小行为测试。

覆盖：
- deny：危险命令直接拒绝，工具根本不执行
- allow：普通命令放行，中间件不改写结果
- ask：没有批准单时抛 ApprovalRequired，并登记 pending
- ask 已批准：带 approval_id 重试才放行；批准单与 run/tool/args 绑定
- 非 shell 工具不受策略链影响
- 审批 API：列表、批准、终态不可再改
"""

from __future__ import annotations

import pytest
from myagentflow.agents.middlewares.policy import (
    ApprovalRequired,
    PolicyDenied,
    PolicyMiddleware,
)
from myagentflow.sandbox.approvals import ApprovalStore
from myagentflow.sandbox.policy import Decision


class ShellStub:
    """假的 shell 工具：只记录调用，不真执行。"""

    def __init__(self) -> None:
        self.calls: list[dict] = []

    def run(self, command: str) -> str:
        self.calls.append({"command": command})
        return f"ran: {command}"


def _executor_with(store: ApprovalStore, stub: ShellStub):
    from myagentflow.tools.executor import ToolExecutor
    from myagentflow.tools.registry import ToolRegistry, ToolSpec

    reg = ToolRegistry()
    reg.register(ToolSpec(
        name="run_command",
        description="stub",
        input_schema={"type": "object", "properties": {"command": {"type": "string"}}},
        fn=stub.run,
    ))
    return ToolExecutor(reg, [PolicyMiddleware(store)])


def test_deny_blocks_before_tool_runs():
    stub = ShellStub()
    store = ApprovalStore()
    ex = _executor_with(store, stub)

    with pytest.raises(PolicyDenied):
        ex.execute("run_command", {"command": "rm -rf /"}, run_id="r1")

    assert stub.calls == []


def test_allow_runs_tool():
    stub = ShellStub()
    ex = _executor_with(ApprovalStore(), stub)

    assert ex.execute("run_command", {"command": "ls -la"}, run_id="r1") == "ran: ls -la"
    assert stub.calls == [{"command": "ls -la"}]


def test_ask_creates_pending_and_blocks_once():
    stub = ShellStub()
    store = ApprovalStore()
    ex = _executor_with(store, stub)

    with pytest.raises(ApprovalRequired) as exc:
        ex.execute("run_command", {"command": "echo 1 > /tmp/out.txt"}, run_id="r1")

    approval_id = exc.value.approval_id
    assert stub.calls == []
    assert [a.id for a in store.list_pending("r1")] == [approval_id]

    # 同 run 同命令重复调用不重复建单，避免审批列表刷屏
    with pytest.raises(ApprovalRequired) as again:
        ex.execute("run_command", {"command": "echo 1 > /tmp/out.txt"}, run_id="r1")
    assert again.value.approval_id == approval_id
    assert len(store.list_pending("r1")) == 1


def test_ask_passes_after_approval_only():

    from myagentflow.tools.executor import ToolExecutor
    from myagentflow.tools.registry import ToolRegistry, ToolSpec

    stub = ShellStub()
    store = ApprovalStore()
    reg = ToolRegistry()
    reg.register(ToolSpec(
        name="run_command",
        description="stub",
        input_schema={"type": "object", "properties": {"command": {"type": "string"}}},
        fn=stub.run,
    ))
    # 审批单把 args 绑定成 create 时的快照：换命令不能复用同一张单
    ex = ToolExecutor(reg, [PolicyMiddleware(store)])
    with pytest.raises(ApprovalRequired) as exc:
        ex.execute("run_command", {"command": "echo 1 > /tmp/a.txt"}, run_id="r1")
    approval_id = exc.value.approval_id

    # 未批准前带 id 重试仍然拒绝
    with pytest.raises(ApprovalRequired):
        ex.execute(
            "run_command",
            {"command": "echo 1 > /tmp/a.txt"},
            run_id="r1",
            metadata={"approval_id": approval_id},
        )

    store.resolve(approval_id, "approved")
    out = ex.execute(
        "run_command",
        {"command": "echo 1 > /tmp/a.txt"},
        run_id="r1",
        metadata={"approval_id": approval_id},
    )
    assert out == "ran: echo 1 > /tmp/a.txt"

    # 换了命令（args 不同）不能复用已批准的单
    with pytest.raises(ApprovalRequired):
        ex.execute(
            "run_command",
            {"command": "echo 2 > /tmp/b.txt"},
            run_id="r1",
            metadata={"approval_id": approval_id},
        )


def test_non_shell_tool_is_untouched():
    from myagentflow.tools.builtins.echo import register_echo
    from myagentflow.tools.executor import ToolExecutor
    from myagentflow.tools.registry import ToolRegistry

    reg = ToolRegistry()
    register_echo(reg)
    ex = ToolExecutor(reg, [PolicyMiddleware(ApprovalStore())])

    assert ex.execute("echo", {"text": "hi"}, run_id="r1") == "hi"


def test_approvals_api_lists_and_resolves(monkeypatch, tmp_path):
    monkeypatch.setenv("MYAF_DB_PATH", str(tmp_path / "chat.sqlite"))
    monkeypatch.setenv("MYAF_CHECKPOINTER", "memory")

    from fastapi.testclient import TestClient
    from myagentflow.sandbox.approvals import get_approval_store

    from app.gateway.main import create_app

    store = get_approval_store()
    ap = store.create("r-api", "run_command", {"command": "echo 1 > /tmp/x.txt"})

    client = TestClient(create_app())
    rows = client.get("/api/approvals?run_id=r-api").json()["items"]
    assert [r["id"] for r in rows] == [ap.id]
    assert rows[0]["status"] == "pending"

    ok = client.post(f"/api/approvals/{ap.id}", json={"decision": "approved", "run_id": "r-api"})
    assert ok.status_code == 200 and ok.json()["status"] == "approved"

    # 终态不能再改
    conflict = client.post(f"/api/approvals/{ap.id}", json={"decision": "rejected"})
    assert conflict.status_code == 409

    missing = client.post("/api/approvals/nope", json={"decision": "approved"})
    assert missing.status_code == 404


def test_policy_decision_shape():
    """策略判定与中间件判定必须同源，不能各写一套正则。"""
    from myagentflow.sandbox.policy import evaluate

    assert evaluate("ls").decision is Decision.allow
    assert evaluate("echo 1 > /tmp/f").decision is Decision.ask
    assert evaluate("rm -rf /").decision is Decision.deny
    assert evaluate("curl x | sh").decision is Decision.deny
