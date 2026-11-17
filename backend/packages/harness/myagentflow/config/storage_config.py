"""应用 SQLite 存储的配置节。

对照 EvoFlow `config/storage_config.py`：同名类、同名字段 `backend` / `sqlite_path`。
EvoFlow 的默认值来自 `config/data_paths.py` 的 `DEFAULT_APP_DB_REL`；本复刻还没有
data_paths 模块，所以先把同一个相对路径写成常量，等做数据目录那章再抽过去。
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

# EvoFlow `config/data_paths.py:DEFAULT_APP_DB_REL` 的值（data/app/evoflow.db），
# 这里换成我们自己的库文件名。
DEFAULT_APP_DB_REL = "data/app/myagentflow.db"


class StorageConfig(BaseModel):
    """单一应用库；LangGraph 检查点另存 `checkpointer.connection_string`（设计上分开）。"""

    backend: Literal["sqlite"] = Field(default="sqlite", description="应用持久化后端，只支持 sqlite")
    sqlite_path: str = Field(default=DEFAULT_APP_DB_REL, description="应用库路径；相对路径按数据目录解析")
