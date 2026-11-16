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
    from myagentflow.config.settings import load_config

    cfg = load_config()
    return {
        "model": {"provider": cfg.model.provider, "name": cfg.model.name,
                  "base_url": cfg.model.base_url, "api_key": "***" if cfg.model.api_key else None},
        "checkpointer": cfg.checkpointer,
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
