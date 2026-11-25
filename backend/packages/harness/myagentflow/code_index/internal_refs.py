"""一、文件说明
    内部引用抽取：在 Python 文件里找「调用了工作区另一个文件里的符号」的位置。
    为什么只做 Python：本章代码索引先覆盖本项目自己的 Python 代码；JS/TS 的跨文件绑定留到后续。

二、目录结构
    packages/harness/myagentflow/code_index/
    ├── __init__.py
    ├── tokenize.py  轻量分词
    ├── symbols.py  符号抽取
    ├── import_bindings.py  import 别名
    ├── internal_refs.py  ← 本文件
    ├── store.py  索引与查询
    └── format_results.py  结果转文本

三、关键方法
    extract_internal_refs()       入口：源码 → from/to/line/symbol。
    extract_python_internal_refs() AST 入口，依赖 import 别名解析。
"""

from __future__ import annotations

import ast
from pathlib import Path

from myagentflow.code_index.import_bindings import python_import_aliases


def extract_internal_refs(
    workspace_root: str | Path | None,
    relative_path: str,
    text: str,
    *,
    for_full_build: bool = False,
) -> list[dict]:
    """抽取内部调用引用；非 Python 文件当前返回空列表。"""
    del for_full_build
    if not str(relative_path).endswith(".py") or not workspace_root:
        return []
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return []
    return extract_python_internal_refs(tree, relative_path, workspace_root)


def extract_python_internal_refs(
    tree: ast.AST,
    from_rel: str | Path,
    workspace_root: str | Path,
) -> list[dict]:
    """遍历 AST 的 Call，把 import 别名解析成目标文件并记录调用行。"""
    root = Path(workspace_root).resolve()
    aliases = python_import_aliases(tree, from_rel, root)
    from_posix = Path(from_rel).as_posix()
    out: list[dict] = []
    seen: set[tuple[str, int, str, str]] = set()

    def add(to_path: str, line: int, symbol: str) -> None:
        key = (to_path, line, symbol, "call")
        if key in seen:
            return
        seen.add(key)
        out.append(
            {
                "from_path": from_posix,
                "to_path": to_path,
                "line": line,
                "ref_kind": "call",
                "symbol": symbol,
            }
        )

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Name) and func.id in aliases:
            add(aliases[func.id], int(node.lineno), func.id)
        elif isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
            base = func.value.id
            if base in aliases:
                add(aliases[base], int(node.lineno), func.attr)
    return out
