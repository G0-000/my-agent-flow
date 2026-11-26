"""渠道事件入口：飞书 Webhook 的最小闭环。

链路：飞书 POST 事件 → 校验 token → 解析文本 → MessageBus → Agent → 飞书发回。
未做：加密事件（Encrypt Key）、事件排队、多租户凭证管理。
"""
from __future__ import annotations

import logging
import os
from collections import OrderedDict
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from app.channels.feishu import FeishuChannel, parse_message_event
from app.channels.message_bus import MessageBus
from app.channels.service import ChannelService, agent_reply

logger = logging.getLogger(__name__)
router = APIRouter()

_service: ChannelService | None = None
_seen_events: OrderedDict[str, None] = OrderedDict()
_SEEN_LIMIT = 500


def _build_service() -> ChannelService:
    bus = MessageBus()
    bus.register(FeishuChannel())
    bus.set_handler(agent_reply)
    return ChannelService(bus)


def get_channel_service() -> ChannelService:
    global _service
    if _service is None:
        _service = _build_service()
    return _service


def install_channel_service(service: ChannelService) -> None:
    """测试/自定义装配入口：换掉单例，不碰真实飞书。"""
    global _service
    _service = service


def reset_channel_service() -> None:
    global _service
    _service = None
    _seen_events.clear()


def _verify_token(payload: dict[str, Any]) -> None:
    """配了 FEISHU_VERIFICATION_TOKEN 就强校验；没配视为本地开发。"""
    expected = (os.getenv("FEISHU_VERIFICATION_TOKEN") or "").strip()
    if not expected:
        return
    got = str((payload.get("header") or {}).get("token") or payload.get("token") or "")
    if got != expected:
        raise HTTPException(status_code=401, detail="verification token 不匹配")


def _first_time(event_id: str) -> bool:
    """飞书会重推事件；内存去重挡住同一进程内的重复回答。"""
    if not event_id:
        return True
    if event_id in _seen_events:
        return False
    _seen_events[event_id] = None
    while len(_seen_events) > _SEEN_LIMIT:
        _seen_events.popitem(last=False)
    return True


@router.post("/channels/feishu/events")
async def feishu_events(request: Request) -> dict[str, Any]:
    payload = await request.json()
    _verify_token(payload)

    # 飞书配置回调地址时会先发 url_verification，必须原样回 challenge。
    if str(payload.get("type") or "") == "url_verification":
        return {"challenge": str(payload.get("challenge") or "")}

    header = payload.get("header") or {}
    if str(header.get("event_type") or "") != "im.message.receive_v1":
        return {"ok": True, "ignored": "event_type"}

    event_id = str(header.get("event_id") or "")
    if not _first_time(event_id):
        return {"ok": True, "ignored": "duplicate"}

    msg = parse_message_event(payload)
    if msg is None:
        return {"ok": True, "ignored": "non_text"}

    try:
        reply = await get_channel_service().handle(msg)
    except Exception:
        logger.exception("feishu handle failed: chat=%s", msg.chat_id)
        # 回 200 避免飞书无限重推；错误留在日志与返回体里。
        return {"ok": False, "error": "agent_failed"}
    return {"ok": True, "reply_chars": len(reply)}
