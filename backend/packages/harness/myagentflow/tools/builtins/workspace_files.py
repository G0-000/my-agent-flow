"""宿主文件工具：读、写、列目录；所有路径先过 workspace 守卫。"""
from __future__ import annotations

import os
from pathlib import Path

from myagentflow.tools.host_direct.workspace_path_guard import Policy, resolve
from myagentflow.tools.registry import ToolRegistry, ToolSpec


def workspace_root() -> Path:
    root = Path(os.getenv("MYAF_WORKSPACE") or ".myaf/workspace").expanduser()
    root.mkdir(parents=True, exist_ok=True)
    return root.resolve()


def _safe(path: str) -> Path:
    r = resolve(path, workspace_root(), Policy.confine)
    if not r.inside:
        raise PermissionError(f"路径越出 workspace：{path}")
    return r.path


def read_file(path: str, offset: int = 0, limit: int = 4000) -> str:
    p = _safe(path)
    if not p.is_file():
        raise FileNotFoundError(str(p))
    lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
    start = max(0, int(offset))
    end = start + max(1, int(limit))
    return "\n".join(lines[start:end])


def write_file(path: str, content: str) -> str:
    p = _safe(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return f"written: {p} ({len(content)} chars)"


def list_dir(path: str = ".") -> str:
    p = _safe(path)
    if not p.is_dir():
        raise NotADirectoryError(str(p))
    entries = sorted(p.iterdir(), key=lambda x: (x.is_file(), x.name))
    return "\n".join(f"{'d' if e.is_dir() else 'f'} {e.name}" for e in entries)


def register_workspace_files(registry: ToolRegistry) -> None:
    registry.register(ToolSpec(
        name="read_file",
        description="读取 workspace 内文本文件；offset/limit 以行计。",
        input_schema={
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "offset": {"type": "integer", "minimum": 0},
                "limit": {"type": "integer", "minimum": 1},
            },
            "required": ["path"],
        },
        fn=read_file,
    ))
    registry.register(ToolSpec(
        name="write_file",
        description="写入 workspace 内文本文件；父目录不存在会自动创建。",
        input_schema={
            "type": "object",
            "properties": {"path": {"type": "string"}, "content": {"type": "string"}},
            "required": ["path", "content"],
        },
        fn=write_file,
    ))
    registry.register(ToolSpec(
        name="list_dir",
        description="列出 workspace 内目录的直接子项。",
        input_schema={"type": "object", "properties": {"path": {"type": "string"}}},
        fn=list_dir,
    ))
