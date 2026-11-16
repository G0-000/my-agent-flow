"""模型工厂：配置进、模型出。

惰性 import 的理由：没配模型的人（只跑测试）不该被迫安装 langchain-openai。
"""
from __future__ import annotations

from typing import Any

from myagentflow.config.settings import ModelConfig


def build_chat_model(cfg: ModelConfig) -> Any:
    if cfg.provider == "openai":
        try:
            from langchain_openai import ChatOpenAI
        except ImportError as exc:
            raise RuntimeError("需要 langchain-openai。安装：uv add langchain-openai") from exc

        # temperature=0：本章的目标是「可复现」，先不谈创造性
        return ChatOpenAI(
            model=cfg.name,
            base_url=cfg.base_url,
            api_key=cfg.api_key,
            temperature=0,
        )

    raise RuntimeError(f"暂不支持的 provider：{cfg.provider}（已实现 openai）")
