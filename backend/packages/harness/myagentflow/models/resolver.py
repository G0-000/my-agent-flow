"""模型选择：把「这一轮该用哪个模型」算出来。

对照 EvoFlow `models/resolver.py`：同名异常 `NoChatModelConfiguredError`（`:38`）、
同名函数 `resolve_run_model`（`:63`）、`get_app_config_safe`（`:190`）、
`_global_default_model`（`:200`）。

本复刻只保留两层来源：运行时覆盖（cfg["model"] / cfg["model_name"]）→ 全局默认
（primary_model → models[0]）。agent 维度、DB 模型库等 EvoFlow 还有的分层等后续章节补。
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any


class NoChatModelConfiguredError(RuntimeError):
    """没有任何可用模型时抛出（对齐 EvoFlow `models/resolver.py:38`）。"""


def get_app_config_safe() -> Any:
    """Best-effort :func:`get_app_config` access; returns ``None`` if unbuilt."""
    try:
        from myagentflow.config.app_config import get_app_config

        return get_app_config()
    except Exception:  # 读配置失败不该在「取模型」这一步炸掉整个链路
        return None


def _global_default_model() -> str:
    """全局默认：primary_model 优先，退回 models[0].name。取不到返回空串。"""
    cfg = get_app_config_safe()
    if cfg is None:
        return ""
    primary = (getattr(cfg, "primary_model", None) or "").strip()
    if primary:
        return primary
    models = getattr(cfg, "models", None) or []
    if models:
        first = getattr(models[0], "name", None)
        if first:
            return str(first).strip()
    return ""


def _runtime_override(cfg: Mapping[str, Any] | None) -> str:
    """运行时覆盖层：cfg 里显式传了 model/model_name 就用它（EvoFlow 同函数名）。"""
    if not cfg:
        return ""
    for key in ("model", "model_name"):
        raw = cfg.get(key)
        if isinstance(raw, str) and raw.strip():
            return raw.strip()
    return ""


def resolve_run_model(
    *,
    agent_code: str | None = None,
    cfg: Mapping[str, Any] | None = None,
    require_configured: bool = True,
) -> str:
    """Resolve the model name that the next chat turn should use.

    本复刻里 ``agent_code`` 暂不参与选择（还没有 agent 维度配置），
    保留参数是为了以后加层时调用方不用改签名。
    """
    runtime_name = _runtime_override(cfg)
    name = runtime_name or _global_default_model()
    if not name and require_configured:
        raise NoChatModelConfiguredError(
            "未配置任何模型：在 config.yaml 写 primary_model，或设 MYAF_MODEL_NAME"
        )
    return name
