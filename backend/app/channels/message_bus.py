"""消息总线：IM 渠道与 Agent 调度之间的解耦层。

对齐 EvoFlow `app/channels/message_bus.py` 的最小版：
入站消息统一成 `InboundMessage`，出站统一成 `OutboundMessage`，
渠道只负责「收」与「发」，调度器只负责「把入站变出站」。
"""
from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from app.channels.base import Channel


class InboundMessageType(StrEnum):
    """入站消息类型；命令消息（/new、/help）与普通聊天分开。"""

    CHAT = "chat"
    COMMAND = "command"


@dataclass
class InboundMessage:
    """一条来自 IM 的消息；thread_id 决定它落到哪个 Agent 会话。"""

    channel_name: str
    chat_id: str
    text: str
    user_id: str = ""
    msg_type: InboundMessageType = InboundMessageType.CHAT
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def thread_id(self) -> str:
        """同一聊天窗口共用一个 thread；换 topic 时由 metadata.topic_id 扩展。"""
        topic = str(self.metadata.get("topic_id") or "").strip()
        base = f"{self.channel_name}:{self.chat_id}"
        return f"{base}#{topic}" if topic else base


@dataclass
class OutboundMessage:
    """一条要发回 IM 的消息；is_final 预留给流式分段。"""

    channel_name: str
    chat_id: str
    text: str
    is_final: bool = True


ReplyHandler = Callable[[InboundMessage], str | Awaitable[str]]


class MessageBus:
    """渠道注册表 + 入站分发；一个进程内一条总线。"""

    def __init__(self) -> None:
        self._channels: dict[str, Channel] = {}
        self._handler: ReplyHandler | None = None

    def register(self, channel: Channel) -> None:
        self._channels[channel.name] = channel

    def set_handler(self, handler: ReplyHandler) -> None:
        self._handler = handler

    def channel(self, name: str) -> Channel:
        ch = self._channels.get(name)
        if ch is None:
            raise KeyError(f"未知渠道：{name}")
        return ch

    async def publish_inbound(self, msg: InboundMessage) -> OutboundMessage:
        """入站 → 调度器 → 出站；没有 handler 时抛错，不静默丢消息。"""
        if self._handler is None:
            raise RuntimeError("MessageBus 没有设置 handler")
        result = self._handler(msg)
        if inspect.isawaitable(result):
            result = await result
        reply = OutboundMessage(
            channel_name=msg.channel_name,
            chat_id=msg.chat_id,
            text=str(result or ""),
            is_final=True,
        )
        self.channel(msg.channel_name).send(msg.thread_id, reply.text)
        return reply
