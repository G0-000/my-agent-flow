"""一、文件说明
    应用根配置：把各配置节拼起来，并负责加载与缓存。
    配置文件不是一个：`app_config.py` 只是根对象，子配置各在自己的文件里：
    字段分区只保留 6 个：log_level / models / primary_model / checkpointer / storage / mcp；
    沙箱、web、技能、可观测等分区等读到对应章节再加，字段名保持同一套。
    缓存按文件 mtime 判断：配置改完不用重启，下一次 get_app_config() 自动重读。

二、目录结构
    packages/harness/myagentflow/config/
    ├── __init__.py
    ├── app_config.py  ← 本文件
    ├── checkpointer_config.py  LangGraph 检查点的配置节：存哪种后端、连到哪。
    ├── model_config.py  单个模型的配置：连接信息 + 采样参数。
    ├── models_yaml.py  YAML 里 `models` 的两种写法：嵌套 `providers` 与扁平
    ├── mcp_config.py  MCP 服务器声明：servers 列表 + 免审批 allow 白名单。
    └── storage_config.py  应用 SQLite 存储配置：只回答「应用库放哪」。

三、关键方法
    AppConfig                     应用根配置。
    _get_config_mtime()           文件不存在返回 None——缺文件不是错误，用默认值照跑。
    _read_config_data()           读 yaml/json。yaml 是可选依赖：没装就退化成「只有默认值」。
    _models_from_env()            没有 config.yaml 时的兜底来源：环境变量（空字符串一律当「没配」）。
    _load_and_cache_app_config()  解析一次并缓存；文件改了由 get_app_config() 触发重读。
    get_app_config()              取配置；文件 mtime 变了就重读，否则返回缓存对象。
    reload_app_config()           强制重读（改完配置立即生效用）。
    reset_app_config()            清缓存，下次 get_app_config() 重新加载。
    set_app_config()              直接注入配置对象（测试替身用）。
"""
from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from myagentflow.config.checkpointer_config import CheckpointerConfig
from myagentflow.config.mcp_config import McpConfig
from myagentflow.config.model_config import ModelConfig
from myagentflow.config.models_yaml import coerce_models_field_for_appconfig
from myagentflow.config.storage_config import StorageConfig

# 覆盖配置路径的环境变量：有值时优先于 ./config.yaml
CONFIG_PATH_ENV = "MYAGENTFLOW_CONFIG_PATH"


class AppConfig(BaseModel):
    """应用根配置。"""

    log_level: str = Field(default="info", description="debug/info/warning/error")
    models: list[ModelConfig] = Field(default_factory=list, description="可用模型列表")
    primary_model: str | None = Field(default=None, description="主模型条目名（字符串，不是对象）")
    checkpointer: CheckpointerConfig = Field(default_factory=CheckpointerConfig)
    storage: StorageConfig = Field(default_factory=StorageConfig)
    mcp: McpConfig = Field(default_factory=McpConfig, description="MCP 外部工具服务器：结构化配置；环境变量只做运行时覆盖")

    model_config = ConfigDict(extra="allow")

    @field_validator("models", mode="before")
    @classmethod
    def _coerce_models(cls, raw: Any) -> Any:
        """models 允许两种写法：扁平列表，或 `{providers: {网关: {..., models: [...]}}}`。

        摊平逻辑在 `config/models_yaml.py`，根对象只负责调用。
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
    """解析一次并缓存；文件改了由 get_app_config() 触发重读。"""
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
    "McpConfig",
    "ModelConfig",
    "StorageConfig",
    "get_app_config",
    "reload_app_config",
    "reset_app_config",
    "set_app_config",
]
