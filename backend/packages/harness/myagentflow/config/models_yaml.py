"""一、文件说明
    YAML 里 `models` 的两种写法：嵌套 `providers` 与扁平列表。
    为什么需要摊平：`AppConfig.models` 是 `list[ModelConfig]`，一条一个模型；
    而 yaml 为了少写重复的 base_url/api_key，习惯按「一个网关」分组写成
    `providers: {网关: {base_url, api_key, models: [...]}}`。两种输入都要能进 Pydantic。
    只做「yaml → 扁平条目」这一个方向；把库里的模型还原成 providers 写回 yaml
    需要模型库，本复刻没有，故不实现。

二、目录结构
    packages/harness/myagentflow/config/
    ├── __init__.py
    ├── app_config.py  应用根配置：把各配置节拼起来，并负责加载与缓存。
    ├── checkpointer_config.py  LangGraph 检查点的配置节：存哪种后端、连到哪。
    ├── model_config.py  单个模型的配置：连接信息 + 采样参数。
    ├── models_yaml.py  ← 本文件
    └── storage_config.py  应用 SQLite 存储配置：只回答「应用库放哪」。

三、关键方法
    infer_vendor_from_connection()       老配置没写 `vendor` 时，从 host 或模型名猜一个。
    _coerce_model_entry()                把列表里的一个元素归一成 dict；无法归一的返回 None（跳过，不报错）。
    _ensure_vendor_field()               条目没写 vendor 就补一个，保证 `ModelConfig.vendor` 尽量非空。
    flatten_providers_dict()             把 `models.providers` 摊平成「一条模型一个 dict」。
    _normalize_models_input()            yaml `models` 的入口：list 走逐条归一，dict 走 providers 摊平，其余给空列表。
    coerce_models_field_for_appconfig()  给 `AppConfig` 的 before-validator 用：把 models 键统一成扁平列表。
"""
from __future__ import annotations

import logging
import re
from typing import Any
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


def infer_vendor_from_connection(base_url: str | None, model_name: str) -> str:
    """老配置没写 `vendor` 时，从 host 或模型名猜一个。

    猜错只影响展示与分组，不影响请求本身（请求只看 base_url + model）。
    """
    if base_url:
        host = (urlparse(base_url).hostname or "").lower()
        if "openai" in host and "azure" not in host:
            return "openai"
        if "anthropic" in host:
            return "anthropic"
        if "deepseek" in host:
            return "deepseek"
        if "google" in host or "generativelanguage" in host:
            return "google"
        if "dashscope" in host or "aliyun" in host:
            return "aliyun"
        if "siliconflow" in host:
            return "siliconflow"
        if "bigmodel" in host or "zhipu" in host:
            return "zhipu"
        if "minimax" in host:
            return "minimax"
        if "volces" in host or "volcengine" in host:
            return "volcengine"
        if "localhost" in host or "127.0.0.1" in host or "ollama" in host:
            return "ollama"
        if "nvidia" in host:
            return "nvidia"
        first = host.split(".")[0] if host else ""
        if first and re.match(r"^[a-z][a-z0-9_-]*$", first):
            return first[:48]
    slug = (model_name or "model").split("-")[0].strip().lower()
    return slug or "default"


def _coerce_model_entry(m: Any) -> dict[str, Any] | None:
    """把列表里的一个元素归一成 dict；无法归一的返回 None（跳过，不报错）。"""
    if m is None:
        return None
    if isinstance(m, dict):
        return dict(m)
    if isinstance(m, str):
        # 裸字符串（只写模型名）不足以造 provider：缺 use/base_url，直接跳过并留日志
        name = m.strip()
        if name:
            logger.warning("Skipping bare string model entry: %r", name)
        return None
    dump = getattr(m, "model_dump", None)
    if callable(dump):
        try:
            d = dump(mode="json")
        except TypeError:
            d = dump()
        return d if isinstance(d, dict) else None
    try:
        d = dict(m)
    except Exception:
        logger.warning("Skipping non-mapping model entry: %s", type(m).__name__)
        return None
    return d if isinstance(d, dict) else None


def _ensure_vendor_field(m: dict[str, Any]) -> dict[str, Any]:
    """条目没写 vendor 就补一个，保证 `ModelConfig.vendor` 尽量非空。"""
    if m.get("vendor"):
        return m
    m = dict(m)
    m["vendor"] = infer_vendor_from_connection(m.get("base_url"), str(m.get("name") or ""))
    return m


def flatten_providers_dict(providers: dict[str, Any]) -> list[dict[str, Any]]:
    """把 `models.providers` 摊平成「一条模型一个 dict」。

    合并规则：provider 层的连接字段（base_url/api_key/use...）作为共享值，
    每条模型自己的字段覆盖共享值；`display_name`/`vendor_label` 是分组标签，
    不往下传（否则同一个网关下所有模型会显示成同一个名字）。
    """
    out: list[dict[str, Any]] = []
    for yaml_key, pdata in providers.items():
        if not isinstance(pdata, dict):
            continue
        sub = pdata.get("models")
        if not isinstance(sub, list) or not sub:
            continue
        vendor = (pdata.get("vendor") or yaml_key or "").strip() or yaml_key
        shared = {k: v for k, v in pdata.items() if k != "models"}
        shared.pop("display_name", None)
        shared.pop("vendor_label", None)
        shared["vendor"] = vendor
        for entry in sub:
            if not isinstance(entry, dict):
                continue
            merged = {**shared, **entry}      # 条目自己的值优先
            merged["vendor"] = vendor
            merged.setdefault("name", entry.get("name"))
            merged.setdefault("model", entry.get("model"))
            out.append(_ensure_vendor_field(merged))
    return out


def _normalize_models_input(raw: Any) -> list[dict[str, Any]]:
    """yaml `models` 的入口：list 走逐条归一，dict 走 providers 摊平，其余给空列表。"""
    if raw is None:
        return []
    if isinstance(raw, list):
        out: list[dict[str, Any]] = []
        for m in raw:
            d = _coerce_model_entry(m)
            if d is None:
                continue
            out.append(_ensure_vendor_field(d))
        return out
    if isinstance(raw, dict) and "providers" in raw:
        return flatten_providers_dict(raw["providers"])
    return []


def coerce_models_field_for_appconfig(raw_models: Any) -> list[dict[str, Any]]:
    """给 `AppConfig` 的 before-validator 用：把 models 键统一成扁平列表。"""
    return _normalize_models_input(raw_models)
