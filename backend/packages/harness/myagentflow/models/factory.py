"""模型工厂：条目名进，模型实例出。

只做「实例化 provider 类」，不发 HTTP；请求由 provider 自己在调用时才发。
目前只实现 openai 一家，其他 vendor 明确报错，不静默退化成假模型。
"""


from __future__ import annotations

from typing import Any

from myagentflow.config.app_config import get_app_config
from myagentflow.config.model_config import ModelConfig
from myagentflow.models.resolver import resolve_run_model


def _entry_by_name(name: str) -> ModelConfig:
    """按条目名在 config.yaml 的 models 里回查这一条。"""
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
        thinking_enabled: 暂不支持 thinking，参数保留以固定调用签名。
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
        # 未配置 temperature 就不传，交给 provider 自己的默认（显式传 None 会被拒）
        if entry.temperature is not None:
            model_kwargs["temperature"] = entry.temperature
        if entry.request_timeout is not None:
            model_kwargs["timeout"] = entry.request_timeout
        if entry.max_retries is not None:
            model_kwargs["max_retries"] = entry.max_retries
        model_kwargs.update(kwargs)
        return ChatOpenAI(**model_kwargs)

    raise RuntimeError(f"暂不支持的 vendor：{entry.vendor}（已实现 openai）")
