"""LangGraph 检查点的配置节：存哪种后端、连到哪。

为什么带模块级单例：provider 每次建图都要取「当前生效的配置」，
让它自己 new 对象会重复开连接；运行中切换后端也由 set_checkpointer_config() 统一改。
"""


from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

# 检查点的存放方式：
#   memory   —— 进程内字典，重启即丢，只适合测试
#   sqlite   —— 单文件库，本地开发默认；需要 langgraph-checkpoint-sqlite
#   postgres —— 多实例共享，需要 langgraph-checkpoint-postgres（本复刻未实现）
CheckpointerType = Literal["memory", "sqlite", "postgres"]


class CheckpointerConfig(BaseModel):
    """Configuration for LangGraph state persistence checkpointer."""

    type: CheckpointerType = Field(
        default="memory",
        description=(
            "后端类型。memory 只在进程内；sqlite 落文件（需要 langgraph-checkpoint-sqlite）；"
            "postgres 需要 langgraph-checkpoint-postgres（本复刻暂未实现）"
        ),
    )
    connection_string: str | None = Field(
        default=None,
        description="sqlite 时为文件路径，如 `.myagentflow/checkpoints.db`；postgres 时为 DSN",
    )


# 全局单例：None 表示没配。provider 从这里取配置，不自己 new 对象
_checkpointer_config: CheckpointerConfig | None = None


def get_checkpointer_config() -> CheckpointerConfig | None:
    """Get the current checkpointer configuration, or None if not configured."""
    return _checkpointer_config


def set_checkpointer_config(config: CheckpointerConfig | None) -> None:
    """Set the checkpointer configuration."""
    global _checkpointer_config
    _checkpointer_config = config
