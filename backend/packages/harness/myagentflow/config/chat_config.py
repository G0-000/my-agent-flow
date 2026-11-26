"""一、文件说明
    聊天入口配置节（04.1）：历史回读的条数等运行时依赖。
    为什么进 config.yaml：回读多少条历史直接影响 token 消耗与回答质量，
    属于部署可调参数；硬编码在路由里既改不了也审计不了。

二、目录结构
    packages/harness/myagentflow/config/
    ├── app_config.py  应用根配置：把各配置节拼起来，并负责加载与缓存。
    └── chat_config.py  ← 本文件

三、关键方法
    ChatConfig  history_limit：聊天入口从消息表回读历史的最大条数。
"""
from __future__ import annotations

from pydantic import BaseModel, Field


class ChatConfig(BaseModel):
    """聊天入口配置：只放与回答质量/成本直接相关的运行时参数。"""

    history_limit: int = Field(
        default=40,
        ge=1,
        description="聊天入口从消息表回读历史的最大条数（取最近 N 条）",
    )
