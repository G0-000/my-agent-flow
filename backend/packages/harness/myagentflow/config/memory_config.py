"""一、文件说明
    记忆抽取配置节（05.4）：后台 worker 的轮询节奏等运行时依赖。
    为什么进 config.yaml：抽取频率是记忆时效与模型开销之间的权衡，
    随部署环境变化；硬编码在 worker 里既改不了也审计不了。

二、目录结构
    packages/harness/myagentflow/config/
    ├── app_config.py  应用根配置：把各配置节拼起来，并负责加载与缓存。
    └── memory_config.py  ← 本文件

三、关键方法
    MemoryConfig  worker_interval：记忆抽取 worker 两轮 tick 的间隔秒数。
"""
from __future__ import annotations

from pydantic import BaseModel, Field


class MemoryConfig(BaseModel):
    """记忆抽取配置：后台 worker 的运行节奏。"""

    worker_interval: float = Field(
        default=5.0,
        gt=0.0,
        description="记忆抽取 worker 两轮 tick 的间隔秒数",
    )
