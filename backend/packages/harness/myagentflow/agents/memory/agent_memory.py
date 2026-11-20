"""一、文件说明
    Agent 记忆：agent 级跨任务，thread 级随线程删。
    为什么读失败返回默认值：记忆是增强项，一条文件坏了不该让整轮对话失败。

二、目录结构
    packages/harness/myagentflow/agents/memory/
    ├── __init__.py
    ├── agent_memory.py  ← 本文件
    ├── prompt.py        记忆注入格式化
    └── ...

三、关键方法
    AgentMemoryManager             读写 agent/task 两层记忆文件。
    get_agent_memory_manager()     进程内按 agent_name 缓存管理器。
    load_agent_memory()            agent 级：facts + context。
    load_task_memory()             thread 级：conversation_history + task_context。
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from myagentflow.config.paths import get_paths

logger = logging.getLogger(__name__)


class AgentMemoryManager:
    """读写 agent/task 两层记忆文件。

    - Agent 记忆：{base_dir}/agents/{agent_name}/memory.json，跨任务、跨会话；
    - Task 记忆：{base_dir}/threads/{thread_id}/agent_memory/{agent_name}.json，随线程删除。
    """

    def __init__(self, agent_name: str | None = None):
        self.agent_name = agent_name
        self.paths = get_paths()

    def get_agent_memory_path(self) -> Path:
        """取 agent 记忆路径；没有 agent_name 时退回全局 memory.json。"""
        if self.agent_name:
            return self.paths.agent_memory_file(self.agent_name)
        return self.paths.memory_file

    def get_task_memory_path(self, thread_id: str) -> Path:
        """取 task 记忆路径；没有 agent_name 时文件名用 global.json。"""
        return (
            self.paths.thread_dir(thread_id)
            / "agent_memory"
            / f"{self.agent_name or 'global'}.json"
        )

    def load_agent_memory(self) -> dict[str, Any]:
        """读 agent 记忆；文件不存在/坏 JSON 都返回空结构。"""
        memory_path = self.get_agent_memory_path()
        if not memory_path.exists():
            return {"facts": [], "context": {}}
        try:
            with open(memory_path, encoding="utf-8") as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            logger.error("Failed to load agent memory: %s", e)
            return {"facts": [], "context": {}}

    def save_agent_memory(self, memory: dict[str, Any]) -> None:
        """写 agent 记忆；写失败只记日志，不抛异常打断对话。"""
        memory_path = self.get_agent_memory_path()
        memory_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with open(memory_path, "w", encoding="utf-8") as f:
                json.dump(memory, f, indent=2, ensure_ascii=False)
            logger.debug("Saved agent memory to %s", memory_path)
        except OSError as e:
            logger.error("Failed to save agent memory: %s", e)

    def load_task_memory(self, thread_id: str) -> dict[str, Any]:
        """读 task 记忆；结构固定为 conversation_history + task_context。"""
        memory_path = self.get_task_memory_path(thread_id)
        if not memory_path.exists():
            return {"conversation_history": [], "task_context": {}}
        try:
            with open(memory_path, encoding="utf-8") as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            logger.error("Failed to load task memory: %s", e)
            return {"conversation_history": [], "task_context": {}}

    def save_task_memory(self, thread_id: str, memory: dict[str, Any]) -> None:
        """写 task 记忆；失败只记日志。"""
        memory_path = self.get_task_memory_path(thread_id)
        memory_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with open(memory_path, "w", encoding="utf-8") as f:
                json.dump(memory, f, indent=2, ensure_ascii=False)
        except OSError as e:
            logger.error("Failed to save task memory: %s", e)

    def get_combined_memory(self, thread_id: str | None = None) -> dict[str, Any]:
        """合并两层：agent_memory 一定返回，task_memory 按 thread_id 可选。"""
        result = {"agent_memory": self.load_agent_memory()}
        if thread_id:
            result["task_memory"] = self.load_task_memory(thread_id)
        return result

    def clear_task_memory(self, thread_id: str) -> None:
        """删 task 记忆文件；线程删除时调用。"""
        memory_path = self.get_task_memory_path(thread_id)
        if memory_path.exists():
            try:
                memory_path.unlink()
                logger.debug("Cleared task memory for thread %s", thread_id)
            except OSError as e:
                logger.error("Failed to clear task memory: %s", e)

    def add_fact_to_agent_memory(self, fact: str, confidence: float = 1.0) -> None:
        """追加一条事实；同文本已存在则不重复写。"""
        memory = self.load_agent_memory()
        facts = memory.get("facts", [])
        if any(f.get("text") == fact for f in facts):
            logger.debug("Fact already exists: %s", fact)
            return
        path = self.get_agent_memory_path()
        facts.append(
            {
                "text": fact,
                "confidence": confidence,
                "created_at": path.stat().st_mtime if path.exists() else 0,
            }
        )
        memory["facts"] = facts
        self.save_agent_memory(memory)

    def add_to_task_history(self, thread_id: str, role: str, content: str) -> None:
        """追加一条 task 对话历史。"""
        memory = self.load_task_memory(thread_id)
        history = memory.get("conversation_history", [])
        history.append({"role": role, "content": content})
        memory["conversation_history"] = history
        self.save_task_memory(thread_id, memory)


# 进程内缓存：同一 agent_name 复用同一个管理器
_agent_memory_managers: dict[str | None, AgentMemoryManager] = {}


def get_agent_memory_manager(agent_name: str | None = None) -> AgentMemoryManager:
    """取/建 agent 记忆管理器；按 agent_name 缓存。"""
    if agent_name not in _agent_memory_managers:
        _agent_memory_managers[agent_name] = AgentMemoryManager(agent_name)
    return _agent_memory_managers[agent_name]
