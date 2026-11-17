"""设置页接口：读配置（脱敏）、改配置（白名单）、热生效。"""
from __future__ import annotations

import os

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()

_ALLOWED = {"MYAF_MODEL_NAME", "MYAF_MODEL_BASE_URL", "MYAF_CHECKPOINTER"}


class SettingsIn(BaseModel):
    values: dict[str, str]


@router.get("/settings")
def read_settings() -> dict:
    from myagentflow.config.app_config import get_app_config

    cfg = get_app_config()
    entry = next((m for m in cfg.models if m.name == cfg.primary_model), None)
    return {
        "model": {
            "vendor": entry.vendor if entry else None,
            "name": cfg.primary_model,
            "base_url": entry.base_url if entry else None,
            "api_key": "***" if entry and entry.api_key else None,
        },
        "checkpointer": cfg.checkpointer.model_dump(),
    }


@router.put("/settings")
def write_settings(body: SettingsIn) -> dict:
    changed = {}
    for key, value in body.values.items():
        if key not in _ALLOWED:
            raise ValueError(f"不允许修改：{key}")     # 白名单：防止改 PATH 之类
        os.environ[key] = value
        changed[key] = value

    from myagentflow.agents.checkpointer.provider import reset_checkpointer

    reset_checkpointer()          # 配置变了：让下次 get_checkpointer() 重建
    return {"changed": changed}
