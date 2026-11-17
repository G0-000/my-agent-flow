"""应用 SQLite 存储配置：只回答「应用库放哪」。

LangGraph 检查点不在这里——那是 checkpointer 的事，两者故意分开：
换检查点后端时不该动应用数据，反之亦然。
"""


from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

# 应用库默认路径：相对数据目录；换成统一的数据目录模块后由它提供。
DEFAULT_APP_DB_REL = "data/app/myagentflow.db"


class StorageConfig(BaseModel):
    """单一应用库；LangGraph 检查点另存 `checkpointer.connection_string`（设计上分开）。"""

    backend: Literal["sqlite"] = Field(default="sqlite", description="应用持久化后端，只支持 sqlite")
    sqlite_path: str = Field(default=DEFAULT_APP_DB_REL, description="应用库路径；相对路径按数据目录解析")
