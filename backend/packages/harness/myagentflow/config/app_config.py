"""应用配置：EvoFlow `config/app_config.py` 的最小复刻。

EvoFlow 把配置拆成多个文件，我们也按同样布局拆（不是挤在一个文件里）：

    config/app_config.py           ← 本文件：AppConfig 根对象 + 加载/缓存
    config/model_config.py         ← ModelConfig（一条模型）
    config/checkpointer_config.py  ← CheckpointerConfig + 单例 get/set
    config/storage_config.py       ← StorageConfig（应用库）

`AppConfig` 字段分区从 EvoFlow 的 14 个裁到 5 个（log_level / models / primary_model /
checkpointer / storage），其余（sandbox / web / skills / extensions / tool_search /
observability / data_retention / token_usage / tool_groups）等读到对应章节再补，字段名照抄。

为什么带 mtime 缓存：EvoFlow 的 `get_app_config()` 也是按文件 mtime 决定要不要重读
（`config/app_config.py:486` `_get_config_mtime`、`:494` `_load_and_cache_app_config`）。
"""
from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from myagentflow.config.checkpointer_config import CheckpointerConfig
from myagentflow.config.model_config import ModelConfig
from myagentflow.config.models_yaml import coerce_models_field_for_appconfig
from myagentflow.config.storage_config import StorageConfig

# 配置路径环境变量：EvoFlow 叫 EVOFLOW_CONFIG_PATH，这里只换前缀
CONFIG_PATH_ENV = "MYAGENTFLOW_CONFIG_PATH"


class AppConfig(BaseModel):
    """Config for the application（字段顺序与 EvoFlow `app_config.py:94` 一致）。"""

    log_level: str = Field(default="info", description="debug/info/warning/error")
    models: list[ModelConfig] = Field(default_factory=list, description="可用模型列表")
    primary_model: str | None = Field(default=None, description="主模型条目名（字符串，不是对象）")
    checkpointer: CheckpointerConfig = Field(default_factory=CheckpointerConfig)
    storage: StorageConfig = Field(default_factory=StorageConfig)

    model_config = ConfigDict(extra="allow")

    @field_validator("models", mode="before")
    @classmethod
    def _coerce_models(cls, raw: Any) -> Any:
        """models 允许两种写法：扁平列表，或 `{providers: {网关: {..., models: [...]}}}`。

        对齐 EvoFlow：摊平逻辑放在 `config/models_yaml.py`，根对象只负责调用。
        """
        return coerce_models_field_for_appconfig(raw)

    @classmethod
    def resolve_config_path(cls, config_path: str | None = None) -> Path:
        """配置路径优先级：显式参数 → MYAGENTFLOW_CONFIG_PATH → 当前目录 config.yaml。"""
        if config_path:
            return Path(config_path).expanduser()
        env_path = os.getenv(CONFIG_PATH_ENV, "").strip()
        if env_path:
            return Path(env_path).expanduser()
        return Path.cwd() / "config.yaml"


# ---------------------------------------------------------------- 缓存与加载
_config: AppConfig | None = None
_config_path: Path | None = None
_config_mtime: float | None = None
_lock = threading.RLock()


def _get_config_mtime(config_path: Path) -> float | None:
    """文件不存在返回 None——缺文件不是错误，用默认值照跑（对齐 `app_config.py:486`）。"""
    try:
        return config_path.stat().st_mtime
    except OSError:
        return None


def _read_config_data(config_path: Path) -> dict[str, Any]:
    """读 yaml/json。yaml 是可选依赖：没装就退化成「只有默认值」。"""
    if not config_path.exists():
        return {}
    text = config_path.read_text(encoding="utf-8")
    if config_path.suffix.lower() == ".json":
        return dict(json.loads(text))
    try:
        import yaml  # type: ignore[import-untyped]
    except ImportError:
        return {}
    data = yaml.safe_load(text) or {}
    return data if isinstance(data, dict) else {}


def _models_from_env() -> list[ModelConfig]:
    """没有 config.yaml 时的兜底来源：环境变量（空字符串一律当「没配」）。"""
    name = os.getenv("MYAF_MODEL_NAME", "").strip()
    if not name:
        return []
    model_id = os.getenv("MYAF_MODEL_ID", "").strip() or name
    return [
        ModelConfig(
            vendor=(os.getenv("MYAF_MODEL_VENDOR") or "openai").strip().lower(),
            name=name,
            use="langchain_openai:ChatOpenAI",
            model=model_id,
            base_url=os.getenv("MYAF_MODEL_BASE_URL") or None,
            api_key=os.getenv("MYAF_MODEL_API_KEY") or None,
        )
    ]


def _load_and_cache_app_config(config_path: str | None = None) -> AppConfig:
    """解析一次并缓存（对齐 EvoFlow `app_config.py:494` 同名函数）。"""
    global _config, _config_path, _config_mtime

    path = AppConfig.resolve_config_path(config_path)
    data = _read_config_data(path)
    if not data.get("models"):
        env_models = _models_from_env()
        if env_models:
            data["models"] = [m.model_dump() for m in env_models]
            data.setdefault("primary_model", env_models[0].name)
    cfg = AppConfig(**data)
    _config, _config_path, _config_mtime = cfg, path, _get_config_mtime(path)
    return cfg


def get_app_config() -> AppConfig:
    """取配置；文件 mtime 变了就重读，否则返回缓存对象。"""
    with _lock:
        if _config is None or _config_path is None:
            return _load_and_cache_app_config()
        if _get_config_mtime(_config_path) != _config_mtime:
            return _load_and_cache_app_config(str(_config_path))
        return _config


def reload_app_config(config_path: str | None = None) -> AppConfig:
    """强制重读（改完配置立即生效用）。"""
    return _load_and_cache_app_config(config_path)


def reset_app_config() -> None:
    """清缓存，下次 get_app_config() 重新加载。"""
    global _config, _config_path, _config_mtime
    with _lock:
        _config, _config_path, _config_mtime = None, None, None


def set_app_config(config: AppConfig) -> None:
    """直接注入配置对象（测试替身用）。"""
    global _config
    with _lock:
        _config = config


__all__ = [
    "AppConfig",
    "CheckpointerConfig",
    "ModelConfig",
    "StorageConfig",
    "get_app_config",
    "reload_app_config",
    "reset_app_config",
    "set_app_config",
]
