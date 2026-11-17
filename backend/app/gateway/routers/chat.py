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
    from myagentflow.agents.lead_agent.graph import build_graph
    from myagentflow.config.app_config import get_app_config
    from myagentflow.models.factory import build_chat_model
    from myagentflow.runtime.streaming import stream_graph

    graph = build_graph(build_chat_model(get_app_config().get_model()))

    async def gen():
        # 断线时 StreamingResponse 会取消这个生成器，资源随 with 清理
        async for chunk in stream_graph(
            graph,
            {"messages": [HumanMessage(content=body.text)]},
            {"configurable": {"thread_id": body.thread_id}},
        ):
            yield chunk

    return StreamingResponse(gen(), media_type="text/event-stream")
