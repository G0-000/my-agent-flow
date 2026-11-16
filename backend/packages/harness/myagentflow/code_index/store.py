"""代码索引：用 ast 抽符号，不靠正则。

为什么必须用 ast：注释里的 `def foo` 和字符串里的 `class Bar` 会骗过正则，
索引一旦有两成错，Agent 就会跳到不存在的行。
"""
from __future__ import annotations

import ast
import sqlite3
from pathlib import Path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS symbols (
    path TEXT NOT NULL,
    kind TEXT NOT NULL,
    name TEXT NOT NULL,
    line INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_symbols_name ON symbols(name);
"""


def index_file(py_path: Path) -> list[tuple[str, str, str, int]]:
    tree = ast.parse(py_path.read_text(encoding="utf-8"), filename=str(py_path))
    path = str(py_path)
    out: list[tuple[str, str, str, int]] = [(path, "module", py_path.stem, 1)]
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            out.append((path, "function", node.name, node.lineno))
        elif isinstance(node, ast.ClassDef):
            out.append((path, "class", node.name, node.lineno))
    return out


class CodeIndex:
    def __init__(self, db_path: str | Path):
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.executescript(_SCHEMA)

    def add_file(self, py_path: Path) -> int:
        rows = index_file(py_path)
        self._conn.executemany("INSERT INTO symbols VALUES (?, ?, ?, ?)", rows)
        self._conn.commit()
        return len(rows)

    def find(self, name: str) -> list[dict]:
        rows = self._conn.execute(
            "SELECT path, kind, line FROM symbols WHERE name=? ORDER BY path, line", (name,)
        ).fetchall()
        return [{"path": r[0], "kind": r[1], "line": r[2]} for r in rows]
