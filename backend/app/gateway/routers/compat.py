"""兼容层：OpenAI Chat Completions 形状 → 内部 chat。

为什么要单独一层：第三方客户端只会说 OpenAI 协议，
把兼容逻辑塞进主接口会让主接口到处是 if。
"""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()


class CompatIn(BaseModel):
    model: str = "myaf"
    messages: list[dict]
    stream: bool = False


def _last_user(messages: list[dict]) -> str:
    for m in reversed(messages):
        if m.get("role") == "user":
            return str(m.get("content", ""))
    return ""


@router.post("/v1/chat/completions")
def completions(body: CompatIn) -> dict:
    from langchain_core.messages import HumanMessage
    from myagentflow.agents.lead_agent.graph import build_graph
    from myagentflow.models.factory import create_chat_model

    graph = build_graph(create_chat_model())
    out = graph.invoke(
        {"messages": [HumanMessage(content=_last_user(body.messages))]},
        {"configurable": {"thread_id": "compat"}},
    )
    text = out["messages"][-1].content
    return {
        "id": "chatcmpl-myaf",
        "object": "chat.completion",
        "choices": [{"index": 0, "message": {"role": "assistant", "content": text},
                     "finish_reason": "stop"}],
        "model": body.model,
    }
