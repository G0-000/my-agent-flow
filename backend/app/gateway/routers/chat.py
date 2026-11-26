"""聊天接口：一个 POST，一条 SSE 流。

入口职责按顺序：注册 run → 写 user 消息 → 建图 → 流式回答 → 写 assistant 消息 → 收尾 run。
组件失败不能阻断回答，但 run 状态必须落到终态。
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from myagentflow.session_execution.lifecycle import RunRegistry
from pydantic import BaseModel

logger = logging.getLogger(__name__)
router = APIRouter()
_RUNS = RunRegistry()


class ChatIn(BaseModel):
    thread_id: str = "default"
    text: str
    approval_id: str = ""  # 上一轮被 ask 拦下后，带上批准单重发本轮


class CancelIn(BaseModel):
    thread_id: str = "default"


def _safe_append(thread_id: str, role: str, content: str) -> None:
    """消息落库失败只记日志；聊天回答不能被归档故障阻断。"""
    if not content.strip():
        return
    try:
        from myagentflow.persistence.chat_message_repositories import append_message
        from myagentflow.persistence.session_repositories import upsert_session_row

        if role == "user":
            upsert_session_row(thread_id, title=content.strip()[:40])
        append_message(thread_id, role, content)
    except Exception:
        logger.exception("append_message failed: thread=%s role=%s", thread_id, role)


def _history_from_table(thread_id: str, limit: int = 40):
    """把消息表里的 user/assistant 还原成 LangChain 消息。

    只还原对话正文，不还原 tool 消息：工具结果属于图状态，消息表只归档
    「用户看到的内容」。这也意味着重建历史时不能声称与检查点逐字节一致。
    """
    from langchain_core.messages import AIMessage, HumanMessage
    from myagentflow.persistence.chat_message_repositories import list_messages

    messages = []
    for row in list_messages(thread_id, limit=limit):
        if row["role"] == "user":
            messages.append(HumanMessage(content=row["content"]))
        elif row["role"] == "assistant":
            messages.append(AIMessage(content=row["content"]))
    return messages


def _checkpoint_messages(graph, config) -> list:
    """读检查点里的消息；没有检查点或线程不存在时返回空列表。"""
    try:
        snapshot = graph.get_state(config)
    except Exception:
        return []
    values = getattr(snapshot, "values", None) or {}
    return list(values.get("messages") or [])


def _log_consistency(thread_id: str, checkpoint_messages: list, table_history: list) -> None:
    """比对两套事实源；只告警，不在这里自动修复（修复策略属于 04.2）。"""
    from langchain_core.messages import AIMessage

    if not checkpoint_messages or not table_history:
        return
    checkpoint_ai = [m for m in checkpoint_messages if isinstance(m, AIMessage)]
    table_ai = [m for m in table_history if isinstance(m, AIMessage)]
    if not checkpoint_ai or not table_ai:
        return
    if str(getattr(checkpoint_ai[-1], "content", "")) != str(table_ai[-1].content):
        logger.warning(
            "message table / checkpoint mismatch: thread=%s table=%d checkpoint=%d",
            thread_id,
            len(table_history),
            len(checkpoint_messages),
        )


def _initial_state(graph, config, thread_id: str, text: str, table_history: list) -> dict:
    """决定本轮从哪份历史开始。

    检查点有状态时以检查点为准（它含 tool 消息与图中间态）；
    检查点为空（换了后端、进程重启、或首次请求）时，用消息表回填，
    这样「表里有、图里没有」不会表现为失忆。
    """
    from langchain_core.messages import HumanMessage

    checkpoint_messages = _checkpoint_messages(graph, config)
    if checkpoint_messages:
        _log_consistency(thread_id, checkpoint_messages, table_history)
        return {"messages": [HumanMessage(content=text)]}
    if table_history:
        logger.info(
            "seeding thread from message table: thread=%s messages=%d",
            thread_id,
            len(table_history),
        )
    return {"messages": [*table_history, HumanMessage(content=text)]}


@router.post("/chat")
async def chat(body: ChatIn) -> StreamingResponse:
    from myagentflow.agents.checkpointer import get_checkpointer
    from myagentflow.agents.lead_agent.graph import build_graph
    from myagentflow.agents.lead_agent.prompt import build_system_prompt
    from myagentflow.agents.middlewares.audit import AuditMiddleware
    from myagentflow.agents.middlewares.policy import PolicyMiddleware
    from myagentflow.context.short_term import ContextManager
    from myagentflow.memory.injection import build_memory_context
    from myagentflow.memory.namespaces import user_ns
    from myagentflow.models.factory import create_chat_model
    from myagentflow.runtime.streaming import stream_graph
    from myagentflow.sandbox.approvals import get_approval_store
    from myagentflow.tools.builtins.echo import register_echo
    from myagentflow.tools.builtins.shell import register_shell
    from myagentflow.tools.builtins.workspace_files import register_workspace_files
    from myagentflow.tools.executor import ToolExecutor
    from myagentflow.tools.registry import ToolRegistry

    try:
        run = _RUNS.start(body.thread_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    # 先读历史再写本轮：否则刚写进去的 user 消息会被当成「上一轮」，重复送给模型。
    try:
        table_history = _history_from_table(body.thread_id)
    except Exception:
        logger.exception("read history failed: thread=%s", body.thread_id)
        table_history = []

    # 用户消息先落库：即使模型失败，也能看到用户发过什么。
    _safe_append(body.thread_id, "user", body.text)

    # 本轮先注册最小工具集；后续工具宿主会替换这里，但入口不再是无工具图。
    tools = ToolRegistry()
    register_echo(tools)
    register_workspace_files(tools)
    register_shell(tools)
    # MCP 是可选扩展：没配 MYAF_MCP_SERVERS 就不启动子进程；失败也不影响内置工具。
    try:
        from myagentflow.mcp.assembly import register_configured_mcp_tools

        register_configured_mcp_tools(tools)
    except Exception:
        logger.exception("mcp assembly failed")
    executor = ToolExecutor(
        tools,
        [AuditMiddleware(), PolicyMiddleware(get_approval_store())],
    )

    # 记忆是增强项：召回/快照失败降级为空块，不阻断回答。
    # 身份系统未接前固定 default，不能从 body 取 user_id，否则任意客户端可读别人的记忆。
    try:
        memory_block = build_memory_context(
            [user_ns("default")],
            body.text,
            thread_id=body.thread_id,
        )
    except Exception:
        logger.exception("memory context failed: thread=%s", body.thread_id)
        memory_block = ""

    # 同一模型既做主回答，也做超阈值时的摘要；摘要失败会退化为滑窗。
    model = create_chat_model()
    # 传 checkpointer 后同 thread 的第二轮会带上前一轮消息；上下文策略每轮临时裁剪。
    graph = build_graph(
        model,
        get_checkpointer(),
        tools=tools,
        tool_executor=executor,
        system_prompt=build_system_prompt(memory_block=memory_block),
        context_manager=ContextManager(model=model),
        max_continuations=2,
    )

    # 图建好后再决定从哪份历史开始：检查点优先，空了用消息表回填。
    graph_config = {
        "configurable": {
            "thread_id": body.thread_id,
            "run_id": run.run_id,
            "approval_id": body.approval_id,
        }
    }
    initial_state = _initial_state(
        graph,
        graph_config,
        body.thread_id,
        body.text,
        table_history,
    )

    def on_final(text: str) -> None:
        _safe_append(body.thread_id, "assistant", text)
        # 记忆抽取是旁路：入队失败只记日志，回答已经成功，不能因此报错。
        try:
            from myagentflow.memory.namespaces import user_ns
            from myagentflow.memory.worker import enqueue_exchange

            enqueue_exchange(user_ns("default"), body.thread_id, body.text, text)
        except Exception:
            logger.exception("enqueue memory update failed: thread=%s", body.thread_id)
        _RUNS.finish(run.run_id, "finished")

    def on_error(message: str) -> None:
        logger.error("chat run failed: thread=%s error=%s", body.thread_id, message)
        _RUNS.finish(run.run_id, "error")

    def on_cancel() -> None:
        logger.info("chat run cancelled: thread=%s run=%s", body.thread_id, run.run_id)
        _RUNS.finish(run.run_id, "cancelled")

    async def gen():
        try:
            async for chunk in stream_graph(
                graph,
                initial_state,
                graph_config,
                on_final=on_final,
                on_error=on_error,
                should_cancel=lambda: _RUNS.is_cancelled(run.run_id),
                on_cancel=on_cancel,
            ):
                yield chunk
        finally:
            # 客户端断开时生成器被关闭，run 不能永远停在 running。
            if run.status == "running":
                _RUNS.finish(run.run_id, "cancelled")

    return StreamingResponse(gen(), media_type="text/event-stream")


@router.post("/chat/cancel")
def cancel_chat(body: CancelIn) -> dict[str, str | bool]:
    """给指定 thread 的活跃 run 发取消信号；真正收尾由流式生成器完成。"""
    rec = _RUNS.active_for_thread(body.thread_id)
    if rec is None:
        raise HTTPException(status_code=404, detail=f"thread {body.thread_id} 没有活跃 run")
    if not _RUNS.cancel(rec.run_id):
        raise HTTPException(status_code=409, detail=f"run {rec.run_id} 已无法取消")
    return {"ok": True, "run_id": rec.run_id}
