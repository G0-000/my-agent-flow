"""聊天接口：一个 POST，一条 SSE 流。"""
from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

router = APIRouter()


class ChatIn(BaseModel):
    thread_id: str = "default"
    text: str


@router.post("/chat")
async def chat(body: ChatIn) -> StreamingResponse:
    from langchain_core.messages import HumanMessage
    from myagentflow.agents.checkpointer import get_checkpointer
    from myagentflow.agents.lead_agent.graph import build_graph
    from myagentflow.models.factory import create_chat_model
    from myagentflow.runtime.streaming import stream_graph
    from myagentflow.tools.builtins.echo import register_echo
    from myagentflow.tools.registry import ToolRegistry

    # 本轮先注册最小工具集；后续工具宿主会替换这里，但入口不再是无工具图。
    tools = ToolRegistry()
    register_echo(tools)

    # 传 checkpointer 后同 thread 的第二轮会带上前一轮消息；不传就是无状态单轮。
    graph = build_graph(
        create_chat_model(),
        get_checkpointer(),
        tools=tools,
    )

    async def gen():
        # 断线时 StreamingResponse 会取消这个生成器，资源随 with 清理
        async for chunk in stream_graph(
            graph,
            {"messages": [HumanMessage(content=body.text)]},
            {"configurable": {"thread_id": body.thread_id}},
        ):
            yield chunk

    return StreamingResponse(gen(), media_type="text/event-stream")
