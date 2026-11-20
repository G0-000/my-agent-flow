"""一、文件说明
    用户事项（UserItem）数据模型：个人待办不是可执行 Task，可 0..n 关联 Task。
    状态/优先级用 StrEnum，序列化后就是普通字符串，前端无需再映射。

二、目录结构
    packages/harness/myagentflow/items/
    ├── __init__.py
    ├── models.py  ← 本文件
    ├── store.py   JSON 持久化
    └── service.py CRUD 业务

三、关键方法
    UserItem.to_public_dict()  补 status_label（中文展示）。
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

try:
    from enum import StrEnum
except ImportError:  # pragma: no cover

    class StrEnum(str, Enum):
        pass


class ItemStatus(StrEnum):
    TODO = "todo"
    IN_PROGRESS = "in_progress"
    WAITING = "waiting"
    DONE = "done"
    PARKED = "parked"


class ItemPriority(StrEnum):
    NONE = "none"
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


ITEM_STATUSES = {s.value for s in ItemStatus}
ITEM_PRIORITIES = {p.value for p in ItemPriority}

STATUS_LABEL_ZH = {
    ItemStatus.TODO: "待办",
    ItemStatus.IN_PROGRESS: "进行中",
    ItemStatus.WAITING: "等待中",
    ItemStatus.DONE: "完成",
    ItemStatus.PARKED: "搁置",
}


class UserItem(BaseModel):
    """用户个人事项；extra=ignore，旧数据多余字段不炸。"""

    model_config = ConfigDict(extra="ignore")

    id: str = Field(default="", description="事项 ID")
    title: str = Field(default="", description="标题")
    notes: str = Field(default="", description="备注")
    conclusion: str = Field(default="", description="处理结论（完成后如何收口）")
    status: ItemStatus = Field(default=ItemStatus.TODO)
    priority: ItemPriority = Field(default=ItemPriority.NORMAL)
    due_at: str | None = Field(
        default=None, description="截止日期 ISO8601 或 YYYY-MM-DD"
    )
    tags: list[str] = Field(default_factory=list)
    assignee_intent: str | None = Field(
        default=None, description="意向责任人 agent_code（未派发）"
    )
    assignee_label: str | None = Field(default=None, description="意向责任人显示名")
    linked_task_ids: list[str] = Field(
        default_factory=list, description="关联的可执行 Task id"
    )
    progress: int = Field(default=0, ge=0, le=100)
    source: str = Field(default="user", description="user|xiaomi|migrated_inbox|…")
    source_ref: str | None = Field(
        default=None, description="来源引用（如旧 inbox task id）"
    )
    org_id: str | None = Field(default=None, description="组织 id")
    owner_scope_id: str | None = Field(
        default=None, description="归属 scope，如 personal:<pid>"
    )
    created_by: str | None = Field(default=None, description="创建者 principal_id")
    created_at: str = Field(default="")
    updated_at: str = Field(default="")

    def to_public_dict(self) -> dict[str, Any]:
        d = self.model_dump()
        d["status"] = str(self.status)
        d["priority"] = str(self.priority)
        d["status_label"] = STATUS_LABEL_ZH.get(self.status, str(self.status))
        return d
