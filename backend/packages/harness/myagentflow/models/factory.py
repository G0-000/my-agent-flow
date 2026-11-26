"""一、文件说明
    模型工厂：条目名进，模型实例出。
    只做「实例化 provider 类」，不发 HTTP；请求由 provider 自己在调用时才发。
    目前实现 openai 与 stub（本地替身）；其余 vendor 明确报错。

二、目录结构
    packages/harness/myagentflow/models/
    ├── __init__.py
    ├── factory.py  ← 本文件
    └── resolver.py  模型选择：算出「这一轮该用哪个模型」。

三、关键方法
    _entry_by_name()     按条目名在 config.yaml 的 models 里回查这一条。
    create_chat_model()  按配置造一个 chat model。
"""
from __future__ import annotations

from importlib import import_module
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


def _load_use_class(path: str) -> type:
    """按 use=“包:类名” 动态加载类。"""
    if ":" not in path:
        raise RuntimeError(f"模型 use 字段应为 'package:Class'，收到 {path!r}")
    mod, cls = path.split(":", 1)
    module = import_module(mod)
    try:
        return getattr(module, cls)
    except AttributeError as exc:
        raise RuntimeError(f"找不到 {path!r} 指定的类") from exc


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

    vendor = (entry.vendor or "").strip().lower()
    if vendor == "stub":
        # 本地离线替身，不依赖任何外部包
        UseClass = _load_use_class(entry.use) if entry.use else None
        if UseClass is None:
            from myagentflow.models.providers.stub import StubChatModel as UseClass  # type: ignore
        return UseClass(**kwargs)  # type: ignore[misc]

    if vendor == "openai":
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

    raise RuntimeError(f"暂不支持的 vendor：{entry.vendor}（已实现 openai, stub）")
