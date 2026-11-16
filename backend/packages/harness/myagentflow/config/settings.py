"""配置层：把散落在各处的 os.getenv 收成一个不可变对象。

为什么不随用随读：配置要在启动时校验一次；跑起来后所有代码拿到的必须是同一份值。
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ModelConfig:
    provider: str = "openai"
    name: str = "gpt-4o-mini"
    base_url: str | None = None
    api_key: str | None = None


@dataclass(frozen=True)
class AppConfig:
    model: ModelConfig
    data_dir: Path
    checkpointer: str = "memory"


def load_config() -> AppConfig:
    """读环境变量。空字符串一律当「没配」，避免 base_url="" 这种坑。"""
    return AppConfig(
        model=ModelConfig(
            provider=os.getenv("MYAF_MODEL_PROVIDER", "openai").strip().lower(),
            name=os.getenv("MYAF_MODEL_NAME", "gpt-4o-mini"),
            base_url=os.getenv("MYAF_MODEL_BASE_URL") or None,
            api_key=os.getenv("MYAF_MODEL_API_KEY") or None,
        ),
        data_dir=Path(os.getenv("MYAF_DATA_DIR", ".myaf")).expanduser(),
        checkpointer=os.getenv("MYAF_CHECKPOINTER", "memory").strip().lower(),
    )
