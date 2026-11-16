"""渠道抽象：任何 IM 都只需实现 recv/send。

为什么用统一事件：同一个 Agent 要能同时服务 Web、IM、CLI，
每加一个渠道就改一遍 Agent 是灾难。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Event:
    channel: str
    thread_id: str
    text: str
    raw: dict[str, Any] = field(default_factory=dict)


class Channel(ABC):
    name: str = "channel"

    @abstractmethod
    def send(self, thread_id: str, text: str) -> None: ...


class Bus:
    def __init__(self) -> None:
        self._channels: dict[str, Channel] = {}

    def register(self, channel: Channel) -> None:
        self._channels[channel.name] = channel

    def inbound(self, channel: str, thread_id: str, text: str, raw: dict | None = None) -> Event:
        if channel not in self._channels:
            raise KeyError(f"未知渠道：{channel}")
        return Event(channel=channel, thread_id=f"{channel}:{thread_id}", text=text, raw=raw or {})

    def outbound(self, event: Event, text: str) -> None:
        self._channels[event.channel].send(event.thread_id, text)
