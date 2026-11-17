"""应用配置：EvoFlow `config/app_config.py` 的最小复刻。

改名对照（一个字段都不改名，只做减法）：
    EvoFlow `AppConfig`          → 本文件 `AppConfig`
    EvoFlow `ModelConfig`        → 本文件 `ModelConfig`
    EvoFlow `CheckpointerConfig` → 本文件 `CheckpointerConfig`（同字段：type / connection_string）
    EvoFlow `StorageConfig`      → 本文件 `StorageConfig`（同字段：backend / sqlite_path）
    EvoFlow `EVOFLOW_CONFIG_PATH`→ `MYAGENTFLOW_CONFIG_PATH`

裁掉的字段（对应章节读到再加，不凭空发明）：
    sandbox / web / skills / extensions / tool_search / observability /
    data_retention / token_usage / tool_groups。

为什么带 mtime 缓存：EvoFlow 的 `get_app_config()` 也是按文件 mtime 决定要不要重读
（`config/app_config.py:486` `_get_config_mtime`、`:494` `_load_and_cache_app_config`）。
"""
from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class NoChatModelConfiguredError(RuntimeError):
    """没配任何可用模型时抛出。

    对齐 EvoFlow `models/resolver.py:38` 的同名异常——那边也是 RuntimeError 子类，
    这样上层 `except RuntimeError` 的写法在两边通用。
    """


class ModelConfig(BaseModel):
    """一条模型配置。字段名对齐 EvoFlow `config/model_config.py:78` 的 `ModelConfig`。"""

    name: str = Field(default="gpt-4o-mini", description="模型名，作为唯一键")
    vendor: str = Field(default="openai", description="厂商；EvoFlow 用它区分 provider 族")
    use: str = Field(
        default="langchain_openai:ChatOpenAI",
        description="Python 类路径，形如 `module:Class`（EvoFlow 同名字段语义）",
    )
    base_url: str | None = Field(default=None, description="自建网关时填；空则用 SDK 默认")
    api_key: str | None = Field(default=None, description="密钥；本复刻不做掩码，见第 1 章缺口说明")
    temperature: float = Field(default=0.0, description="本章目标是可复现，默认 0")
    max_tokens: int | None = Field(default=None, description="输出上限；None 交给模型默认")

    # extra="allow"：EvoFlow 允许模型条目带 thinking/availability 等扩展列，
    # 这里同样不拒绝未知字段，避免升级配置时炸掉。
    model_config = ConfigDict(extra="allow")


class CheckpointerConfig(BaseModel):
    """对齐 EvoFlow `config/checkpointer_config.py:10`。"""

    type: Literal["memory", "sqlite"] = Field(
        default="memory",
        description="memory 只活在进程内；sqlite 落文件（需要 langgraph-checkpoint-sqlite）",
    )
    connection_string: str | None = Field(
        default=None,
        description="sqlite 时为文件路径，如 `.myagentflow/checkpoints.db`",
    )


class StorageConfig(BaseModel):
    """对齐 EvoFlow `config/storage_config.py:10`：单一应用库。"""

    backend: Literal["sqlite"] = Field(default="sqlite", description="本复刻只支持 sqlite")
    sqlite_path: str = Field(
        default="data/app/myagentflow.db",
        description="应用库路径；相对路径按数据目录解析",
    )


class AppConfig(BaseModel):
    """配置根对象。字段顺序与 EvoFlow `AppConfig`（`app_config.py:94`）保持一致。"""

    log_level: str = Field(default="info", description="debug/info/warning/error")
    models: list[ModelConfig] = Field(default_factory=list, description="可用模型列表")
    primary_model: str | None = Field(default=None, description="主模型名，对应 models 里的 name")
    checkpointer: CheckpointerConfig = Field(default_factory=CheckpointerConfig)
    storage: StorageConfig = Field(default_factory=StorageConfig)

    model_config = ConfigDict(extra="allow")

    # ---- 取模型：EvoFlow 的 primary_model 是字符串名，靠名字回查列表 ----
    def get_model(self, name: str | None = None) -> ModelConfig:
        """按名字取模型；不传名字就取 primary_model。取不到抛 NoChatModelConfiguredError。"""
        target = (name or self.primary_model or "").strip()
        if not target:
            raise NoChatModelConfiguredError(
                "未配置主模型：在 config.yaml 的 primary_model 写一个名字，或设 MYAF_MODEL_NAME"
            )
        for m in self.models:
            if m.name == target:
                return m
        raise NoChatModelConfiguredError(f"primary_model={target!r} 在 models 里不存在")

    # ---- 配置路径：对齐 EvoFlow resolve_config_path 的优先级 ----
    @classmethod
    def resolve_config_path(cls, config_path: str | None = None) -> Path:
        if config_path:
            return Path(config_path).expanduser()
        env_path = os.getenv("MYAGENTFLOW_CONFIG_PATH", "").strip()
        if env_path:
            return Path(env_path).expanduser()
        return Path.cwd() / "config.yaml"


# ---------------------------------------------------------------- 缓存与加载

_config: AppConfig | None = None
_config_path: Path | None = None
_config_mtime: float | None = None
_lock = threading.RLock()


def _get_config_mtime(config_path: Path) -> float | None:
    """文件不存在返回 None——与 EvoFlow 一致，缺文件不是错误，用默认值。"""
    try:
        return config_path.stat().st_mtime
    except OSError:
        return None


def _read_config_data(config_path: Path) -> dict[str, Any]:
    """读 yaml/json。yaml 依赖是可选安装，缺了就退化成「只有默认值」。"""
    if not config_path.exists():
        return {}
    text = config_path.read_text(encoding="utf-8")
    if config_path.suffix.lower() in {".json"}:
        return json.loads(text)
    try:
        import yaml  # type: ignore[import-untyped]
    except ImportError:
        return {}
    data = yaml.safe_load(text) or {}
    return data if isinstance(data, dict) else {}


def _models_from_env() -> list[ModelConfig]:
    """没 config.yaml 时的最小来源：环境变量。空字符串一律当「没配」。"""
    name = os.getenv("MYAF_MODEL_NAME", "").strip()
    if not name:
        return []
    return [
        ModelConfig(
            name=name,
            vendor=(os.getenv("MYAF_MODEL_VENDOR") or "openai").strip().lower(),
            base_url=os.getenv("MYAF_MODEL_BASE_URL") or None,
            api_key=os.getenv("MYAF_MODEL_API_KEY") or None,
        )
    ]


def _load_and_cache_app_config(config_path: str | None = None) -> AppConfig:
    """解析一次并缓存。对齐 EvoFlow `config/app_config.py:494` 的同名函数。"""
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
        current_mtime = _get_config_mtime(_config_path)
        if current_mtime != _config_mtime:
            return _load_and_cache_app_config(str(_config_path))
        return _config


def reload_app_config(config_path: str | None = None) -> AppConfig:
    """强制重读（测试与「改完配置立即生效」用）。"""
    return _load_and_cache_app_config(config_path)


def reset_app_config() -> None:
    """清缓存，下次 get_app_config() 重新加载。"""
    global _config, _config_path, _config_mtime
    with _lock:
        _config, _config_path, _config_mtime = None, None, None


def set_app_config(config: AppConfig) -> None:
    """直接注入一个配置对象（测试替身用）。"""
    global _config
    with _lock:
        _config = config


__all__ = [
    "AppConfig",
    "CheckpointerConfig",
    "ModelConfig",
    "NoChatModelConfiguredError",
    "StorageConfig",
    "get_app_config",
    "reload_app_config",
    "reset_app_config",
    "set_app_config",
]
