"""开发/测试替身模型：不联网、可预测输出。

用法：在 config.yaml 里把某条模型的 vendor 设为 "stub"，use 可写 "stub:StubChatModel"。
- invoke(): 回显最后一条用户消息，前缀 "echo: "（或固定文本）。
- bind_tools(): 返回 self，满足工具绑定链路（本替身不真的调用工具）。

注意：仅用于本地测试与离线演示，切勿在生产配置中启用。
"""
from __future__ import annotations

from typing import Any

from langchain_core.messages import AIMessage


class StubChatModel:
    """极简 ChatModel 替身：同步回显；可指定固定输出。"""

    def __init__(self, *, fixed_output: str | None = None, prefix: str = "echo: ") -> None:
        self.fixed_output = fixed_output
        self.prefix = prefix

    # 与 LangChain ChatModel 的 bind_tools 签名对齐（最小化）
    def bind_tools(self, _tools: Any, **_kwargs: Any) -> StubChatModel:
        return self

    # 与 ChatModel.invoke 约定对齐：messages 列表进，AIMessage 出
    def invoke(self, messages: list[Any], *_args: Any, **_kwargs: Any) -> AIMessage:
        last = ""
        if messages:
            last_msg = messages[-1]
            last = getattr(last_msg, "content", "")
        text = self.fixed_output if self.fixed_output is not None else f"{self.prefix}{last}"
        return AIMessage(content=text)
