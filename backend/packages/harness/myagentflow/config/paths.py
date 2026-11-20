"""一、文件说明
    数据目录解析：记忆、线程、Agent 文件都从这里取路径。
    为什么集中：路径散落在各模块里，测试要改目录就得 monkeypatch 一堆常量；
    这里只留一个 base_dir 入口，测试改环境变量即可。

二、目录结构
    packages/harness/myagentflow/config/
    ├── __init__.py
    ├── paths.py  ← 本文件
    ├── app_config.py
    └── ...

三、关键方法
    Paths               所有数据路径的根；base_dir 默认 $MYAF_DATA_DIR 或 ~/.myagentflow。
    get_paths()         进程内单例，避免每轮重复解析。
    reset_paths_cache() 测试换目录后清缓存。
"""

from __future__ import annotations

import os
import re
import threading
from pathlib import Path

_SAFE_THREAD_ID_RE = re.compile(r"^[A-Za-z0-9._-]{1,128}$")


class Paths:
    """所有数据路径的根；base_dir 默认 $MYAF_DATA_DIR 或 ~/.myagentflow。"""

    def __init__(self, base_dir: str | Path | None = None) -> None:
        self._base_dir = Path(
            base_dir
            or os.environ.get("MYAF_DATA_DIR")
            or (Path.home() / ".myagentflow")
        )

    @property
    def base_dir(self) -> Path:
        return self._base_dir

    @property
    def memory_file(self) -> Path:
        """全局记忆文件：{base_dir}/memory.json。"""
        return self.base_dir / "memory.json"

    @property
    def agents_dir(self) -> Path:
        return self.base_dir / "agents"

    def agent_dir(self, name: str) -> Path:
        """单个 Agent 目录：{base_dir}/agents/{name}/（名字统一小写）。"""
        return self.agents_dir / name.lower()

    def agent_memory_file(self, name: str) -> Path:
        """Agent 记忆文件：{base_dir}/agents/{name}/memory.json。"""
        return self.agent_dir(name) / "memory.json"

    def thread_dir(self, thread_id: str) -> Path:
        """线程目录：{base_dir}/threads/{thread_id}/；id 做安全校验。"""
        tid = str(thread_id or "").strip()
        if not _SAFE_THREAD_ID_RE.match(tid):
            raise ValueError(f"Invalid thread_id {thread_id!r}")
        return self.base_dir / "threads" / tid


_paths_lock = threading.Lock()
_paths_instance: Paths | None = None


def get_paths() -> Paths:
    """进程内单例，避免每轮重复解析。"""
    global _paths_instance
    with _paths_lock:
        if _paths_instance is None:
            _paths_instance = Paths()
        return _paths_instance


def reset_paths_cache() -> None:
    """测试换目录后清缓存。"""
    global _paths_instance
    with _paths_lock:
        _paths_instance = None
