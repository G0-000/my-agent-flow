"""两层记忆：agent 级跨任务，thread 级随线程删。

为什么读失败要返回默认值而不是抛异常：
记忆是增强项，不是主流程。一条记忆文件写坏了不该让整轮对话失败。
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT = {"facts": [], "context": {}}


def _empty() -> dict[str, Any]:
    """每次返回全新对象：dict(DEFAULT) 是浅拷贝，facts 列表会被所有调用方共享。"""
    return {"facts": [], "context": {}}


def _load(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return {"facts": list(data.get("facts", [])), "context": dict(data.get("context", {}))}
        logger.error("记忆结构不是对象：%s", path)
    except FileNotFoundError:
        return _empty()               # 首次运行：空记忆
    except (json.JSONDecodeError, OSError) as exc:
        logger.error("记忆读取失败 %s：%s", path, exc)
    return _empty()


@dataclass
class AgentMemoryManager:
    base_dir: Path
    agent_name: str = "lead"
    _agent_path: Path = field(init=False)
    _thread_paths: dict[str, Path] = field(default_factory=dict, init=False)

    def __post_init__(self) -> None:
        self._agent_path = self.base_dir / "agents" / self.agent_name / "memory.json"

    def thread_path(self, thread_id: str) -> Path:
        return self.base_dir / "threads" / thread_id / "agent_memory" / f"{self.agent_name}.json"

    def load_agent(self) -> dict[str, Any]:
        return _load(self._agent_path)

    def load_thread(self, thread_id: str) -> dict[str, Any]:
        return _load(self.thread_path(thread_id))

    def remember(self, thread_id: str, fact: str, scope: str = "thread") -> None:
        """写一条事实。scope=agent 时跨任务保留。"""
        path = self._agent_path if scope == "agent" else self.thread_path(thread_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        data = _load(path)
        data["facts"].append(fact)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
