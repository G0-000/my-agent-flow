"""模型工厂：配置进、模型出。

对照 EvoFlow `models/factory.py:879` 的 `create_chat_model(name=None, ...)`：
只做「实例化 provider 类」，不发 HTTP。我们只保留 openai 一家，
其余 vendor 明确报未实现，不静默退化。
"""
from __future__ import annotations

from typing import Any

from myagentflow.config.app_config import get_app_config
from myagentflow.config.model_config import ModelConfig
from myagentflow.models.resolver import resolve_run_model


def _entry_by_name(name: str) -> ModelConfig:
    """按条目名回查模型配置。EvoFlow 里等价于「从库里查模型行」。"""
    cfg = get_app_config()
    for m in cfg.models:
        if m.name == name:
            return m
    raise ValueError(f"config.yaml 的 models 里没有 name={name!r} 这一条")


def create_chat_model(
    name: str | None = None,
    thinking_enabled: bool | None = False,
    **kwargs: Any,
) -> Any:
    """按配置造一个 chat model。

    Args:
        name: 条目名；不传就按 `resolve_run_model()` 的规则解析（primary_model → models[0]）。
        thinking_enabled: 本复刻暂不支持 thinking，参数留着与 EvoFlow 签名一致。
    """
    resolved = (name or "").strip() or resolve_run_model()
    entry = _entry_by_name(resolved)

    if entry.vendor == "openai":
        try:
            from langchain_openai import ChatOpenAI
        except ImportError as exc:
            raise RuntimeError("需要 langchain-openai。安装：uv add langchain-openai") from exc

        model_kwargs: dict[str, Any] = {
            "model": entry.model,          # 请求用 model（模型 ID），不是 name（条目名）
            "base_url": entry.base_url,
            "api_key": entry.api_key,
        }
        # temperature 在 EvoFlow 里是 Optional，未配置就不传，交给 provider 默认
        if entry.temperature is not None:
            model_kwargs["temperature"] = entry.temperature
        if entry.request_timeout is not None:
            model_kwargs["timeout"] = entry.request_timeout
        if entry.max_retries is not None:
            model_kwargs["max_retries"] = entry.max_retries
        model_kwargs.update(kwargs)
        return ChatOpenAI(**model_kwargs)

    raise RuntimeError(f"暂不支持的 vendor：{entry.vendor}（已实现 openai）")
