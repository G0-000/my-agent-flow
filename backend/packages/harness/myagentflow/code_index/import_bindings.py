"""一、文件说明
    Python import 别名解析：把 `from pkg.mod import helper as h` 里的 h 映射到真实文件路径。
    只解析工作区内、能落到 .py 或 __init__.py 的导入；外部包直接忽略，避免误报调用。

二、目录结构
    packages/harness/myagentflow/code_index/
    ├── __init__.py
    ├── tokenize.py  轻量分词
    ├── symbols.py  符号抽取
    ├── import_bindings.py  ← 本文件
    ├── internal_refs.py  内部调用引用
    ├── store.py  索引与查询
    └── format_results.py  结果转文本

三、关键方法
    python_import_aliases()  返回 {本地别名: 相对文件路径}。
    _module_file()           把点分模块名解析成工作区内的文件。
"""

from __future__ import annotations

import ast
from pathlib import Path


def python_import_aliases(
    tree: ast.AST,
    from_rel: str | Path,
    workspace_root: str | Path,
) -> dict[str, str]:
    """收集 Python import 别名；解析不到工作区文件的条目直接跳过。"""
    root = Path(workspace_root).resolve()
    from_path = Path(from_rel)
    aliases: dict[str, str] = {}

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            base_parts = _relative_base(from_path, node.level)
            module_parts = [part for part in (node.module or "").split(".") if part]
            for alias in node.names:
                if alias.name == "*":
                    continue
                local = alias.asname or alias.name
                direct = _module_file(root, [*base_parts, *module_parts, alias.name])
                package = _module_file(root, [*base_parts, *module_parts])
                target = direct or package
                if target:
                    aliases[local] = _rel(target, root)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                parts = [part for part in alias.name.split(".") if part]
                target = _module_file(root, parts)
                if target:
                    aliases[alias.asname or parts[-1]] = _rel(target, root)
    return aliases


def _relative_base(from_path: Path, level: int) -> list[str]:
    """相对导入的基准包：level=1 是当前文件所在包，level=2 往上一层。"""
    if level <= 0:
        return []
    parent_parts = list(from_path.parent.parts)
    trim = max(0, level - 1)
    return parent_parts[: len(parent_parts) - trim] if trim else parent_parts


def _module_file(root: Path, parts: list[str]) -> Path | None:
    """点分模块 → 文件；优先 ``x.py``，再 ``x/__init__.py``。"""
    if not parts:
        return None
    candidate = root.joinpath(*parts).with_suffix(".py")
    if candidate.is_file():
        return candidate
    package = root.joinpath(*parts) / "__init__.py"
    if package.is_file():
        return package
    return None


def _rel(path: Path, root: Path) -> str:
    """工作区内相对路径，统一用 /。"""
    try:
        return path.resolve().relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()
