"""飞书渠道：最小可用实现（Webhook 入站 + 文本回复）。

对齐 EvoFlow `app/channels/feishu.py` 的最小面：
- 入站：解析 `im.message.receive_v1` 文本消息，转成 `InboundMessage`。
- 出站：tenant_access_token + `im/v1/messages` 发文本。
- 传输可注入：测试用假的 `http_post`，不联网。

未做：卡片、图片/文件、@ 机器人鉴权、长连接、事件去重。
"""
from __future__ import annotations

import json
import os
import re
import time
import urllib.parse
import urllib.request
from collections.abc import Callable
from typing import Any

from app.channels.base import Channel
from app.channels.message_bus import InboundMessage, InboundMessageType

FEISHU_BASE_URL = "https://open.feishu.cn"
_MENTION = re.compile(r"@_user_\w+")

HttpPost = Callable[[str, dict[str, Any], dict[str, str]], dict[str, Any]]


class FeishuApiError(RuntimeError):
    """飞书返回非 0 code；带 code 与 msg，便于定位权限/参数问题。"""


def _default_http_post(url: str, payload: dict[str, Any], headers: dict[str, str]) -> dict[str, Any]:
    """最小 JSON POST；不引入 requests/httpx 依赖。"""
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=body, method="POST", headers=headers)
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode("utf-8"))


class FeishuApi:
    """飞书 Open API 的最小客户端：token 缓存 + 发文本。"""

    def __init__(
        self,
        *,
        app_id: str | None = None,
        app_secret: str | None = None,
        base_url: str = FEISHU_BASE_URL,
        http_post: HttpPost | None = None,
    ) -> None:
        self.app_id = app_id if app_id is not None else os.getenv("FEISHU_APP_ID", "")
        self.app_secret = (
            app_secret if app_secret is not None else os.getenv("FEISHU_APP_SECRET", "")
        )
        self.base_url = base_url.rstrip("/")
        self._post = http_post or _default_http_post
        self._token: str = ""
        self._token_expire_at: float = 0.0

    def _post_json(self, path: str, payload: dict[str, Any], headers: dict[str, str]) -> dict[str, Any]:
        return self._post(f"{self.base_url}{path}", payload, headers)

    def tenant_token(self, *, now: float | None = None) -> str:
        """拿 tenant_access_token；提前 60 秒过期，避免请求边界上失效。"""
        now = time.time() if now is None else float(now)
        if self._token and now < self._token_expire_at - 60:
            return self._token
        if not self.app_id or not self.app_secret:
            raise FeishuApiError("缺少 FEISHU_APP_ID / FEISHU_APP_SECRET")
        data = self._post_json(
            "/open-apis/auth/v3/tenant_access_token/internal",
            {"app_id": self.app_id, "app_secret": self.app_secret},
            {"Content-Type": "application/json; charset=utf-8"},
        )
        if int(data.get("code") or 0) != 0:
            raise FeishuApiError(f"tenant token 失败 code={data.get('code')} msg={data.get('msg')}")
        self._token = str(data.get("tenant_access_token") or "")
        self._token_expire_at = now + int(data.get("expire") or 7200)
        return self._token

    def send_text(self, chat_id: str, text: str, *, now: float | None = None) -> dict[str, Any]:
        """按 chat_id 发纯文本；content 必须是 JSON 字符串，不是对象。"""
        token = self.tenant_token(now=now)
        query = urllib.parse.urlencode({"receive_id_type": "chat_id"})
        data = self._post_json(
            f"/open-apis/im/v1/messages?{query}",
            {
                "receive_id": chat_id,
                "msg_type": "text",
                "content": json.dumps({"text": text}, ensure_ascii=False),
            },
            {
                "Content-Type": "application/json; charset=utf-8",
                "Authorization": f"Bearer {token}",
            },
        )
        if int(data.get("code") or 0) != 0:
            raise FeishuApiError(f"发消息失败 code={data.get('code')} msg={data.get('msg')}")
        return data


class FeishuChannel(Channel):
    """渠道实现：入站由路由解析，出站由 `send()` 调 Open API。"""

    name = "feishu"

    def __init__(self, api: FeishuApi | None = None) -> None:
        self.api = api or FeishuApi()

    def send(self, thread_id: str, text: str) -> None:
        chat_id = thread_id.split(":", 1)[1].split("#", 1)[0] if ":" in thread_id else thread_id
        self.api.send_text(chat_id, text)


def parse_message_event(payload: dict[str, Any]) -> InboundMessage | None:
    """解析 `im.message.receive_v1`；非文本/缺 chat_id 返回 None，不抛异常。"""
    event = payload.get("event") or {}
    message = event.get("message") or {}
    if str(message.get("message_type") or "") != "text":
        return None
    chat_id = str(message.get("chat_id") or "").strip()
    if not chat_id:
        return None
    raw_content = message.get("content") or "{}"
    try:
        content = json.loads(raw_content) if isinstance(raw_content, str) else raw_content
    except json.JSONDecodeError:
        return None
    text = str((content or {}).get("text") or "").strip()
    text = _MENTION.sub("", text).strip()
    if not text:
        return None
    sender = (event.get("sender") or {}).get("sender_id") or {}
    return InboundMessage(
        channel_name=FeishuChannel.name,
        chat_id=chat_id,
        text=text,
        user_id=str(sender.get("open_id") or ""),
        msg_type=InboundMessageType.CHAT,
        metadata={"message_id": message.get("message_id"), "event_id": payload.get("header", {}).get("event_id")},
    )
