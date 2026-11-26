"""渠道调度服务：入站消息 → Agent 一轮回答 → 出站。

`ChannelService` 只依赖一个 reply 函数，测试可注入假函数；
生产用 `agent_reply()`，与 `/api/chat` 共用同一套图、工具、记忆。
"""
from __future__ import annotations

import logging

from app.channels.message_bus import InboundMessage, MessageBus

logger = logging.getLogger(__name__)


def _content_to_text(content: object) -> str:
    """模型可能返回字符串或多段 content block，统一压成纯文本。"""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and block.get("type") == "text":
                parts.append(str(block.get("text") or ""))
        return "".join(parts)
    return str(content or "")


async def agent_reply(msg: InboundMessage) -> str:
    """跑一轮非流式 Agent；IM 场景不需要 SSE，直接拿终态回答。"""
    from langchain_core.messages import HumanMessage
    from myagentflow.agents.checkpointer import get_checkpointer
    from myagentflow.agents.lead_agent.graph import build_graph
    from myagentflow.agents.lead_agent.prompt import build_system_prompt
    from myagentflow.agents.middlewares.audit import AuditMiddleware
    from myagentflow.agents.middlewares.policy import PolicyMiddleware
    from myagentflow.context.short_term import ContextManager
    from myagentflow.memory.injection import build_memory_context
    from myagentflow.memory.namespaces import user_ns
    from myagentflow.models.factory import create_chat_model
    from myagentflow.persistence.chat_message_repositories import append_message
    from myagentflow.persistence.session_repositories import upsert_session_row
    from myagentflow.sandbox.approvals import get_approval_store
    from myagentflow.tools.builtins.echo import register_echo
    from myagentflow.tools.builtins.shell import register_shell
    from myagentflow.tools.builtins.workspace_files import register_workspace_files
    from myagentflow.tools.executor import ToolExecutor
    from myagentflow.tools.registry import ToolRegistry

    thread_id = msg.thread_id
    try:
        upsert_session_row(thread_id, title=msg.text.strip()[:40])
        append_message(thread_id, "user", msg.text)
    except Exception:
        logger.exception("channel append user failed: thread=%s", thread_id)

    tools = ToolRegistry()
    register_echo(tools)
    register_workspace_files(tools)
    register_shell(tools)
    executor = ToolExecutor(tools, [AuditMiddleware(), PolicyMiddleware(get_approval_store())])

    try:
        memory_block = build_memory_context([user_ns("default")], msg.text, thread_id=thread_id)
    except Exception:
        logger.exception("channel memory context failed: thread=%s", thread_id)
        memory_block = ""

    model = create_chat_model()
    graph = build_graph(
        model,
        get_checkpointer(),
        tools=tools,
        tool_executor=executor,
        system_prompt=build_system_prompt(memory_block=memory_block),
        context_manager=ContextManager(model=model),
        max_continuations=2,
    )
    result = await graph.ainvoke(
        {"messages": [HumanMessage(content=msg.text)]},
        {
            "configurable": {
                "thread_id": thread_id,
                "channel": msg.channel_name,
                "user_id": msg.user_id,
                "message_id": msg.metadata.get("message_id"),
            }
        },
    )
    text = _content_to_text(result["messages"][-1].content)
    try:
        append_message(thread_id, "assistant", text)
    except Exception:
        logger.exception("channel append assistant failed: thread=%s", thread_id)
    return text


class ChannelService:
    """把总线与回复函数绑在一起；一个进程一个实例。"""

    def __init__(self, bus: MessageBus) -> None:
        self.bus = bus

    async def handle(self, msg: InboundMessage) -> str:
        out = await self.bus.publish_inbound(msg)
        return out.text
