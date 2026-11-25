"""一、文件说明
    符号抽取：Python 用 ast 拿类/函数/方法，其他语言退化为正则；只抽本章查询要用的名字与行号。
    为什么先 AST 再正则：AST 能给出准确行号和嵌套关系，正则只负责 `ast.parse` 失败时的兜底。

二、目录结构
    packages/harness/myagentflow/code_index/
    ├── __init__.py
    ├── tokenize.py  轻量分词
    ├── symbols.py  ← 本文件：符号抽取
    ├── import_bindings.py  import 别名
    ├── internal_refs.py  内部调用引用
    ├── store.py  索引与查询
    └── format_results.py  结果转文本

三、关键方法
    extract_symbols()          文件路径 + 源码 → 符号列表。
    _ast_python_symbols()      Python AST 遍历，记录类、函数、方法。
    _regex_python_symbols()    ast 解析失败时的行级兜底。
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

_PY_DEF_RE = re.compile(r"^\s*(?:async\s+)?(?:def|class)\s+([A-Za-z_][A-Za-z0-9_]*)")
_GENERIC_DEF_RE = re.compile(
    r"^\s*(?:export\s+)?(?:async\s+)?(?:def|class|function|func|interface|type|enum)\s+"
    r"([A-Za-z_$][A-Za-z0-9_$]*)"
)


def extract_symbols(
    workspace_root: str | Path | None,
    relative_path: str,
    text: str,
    *,
    for_full_build: bool = False,
) -> list[dict]:
    """抽取符号；``workspace_root`` 目前只用于统一路径语义，不参与解析。"""
    del workspace_root, for_full_build  # 保持与上游同名参数，当前实现不需要工作区上下文
    path = str(relative_path or "")
    if path.endswith(".py"):
        try:
            tree = ast.parse(text)
        except SyntaxError:
            return _regex_python_symbols(path, text)
        symbols: list[dict] = []
        _walk_python(tree, text, symbols)
        return symbols
    return _generic_symbols(path, text)


def _walk_python(tree: ast.AST, text: str, out: list[dict]) -> None:
    """遍历 Python AST，给每个类/函数/方法补签名与行号。"""
    lines = text.splitlines()

    def visit(node: ast.AST, container: str = "") -> None:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            kind = (
                "class"
                if isinstance(node, ast.ClassDef)
                else ("method" if container else "function")
            )
            symbol = {
                "name": node.name,
                "kind": kind,
                "line": int(node.lineno),
                "end_line": int(
                    getattr(node, "end_lineno", node.lineno) or node.lineno
                ),
                "signature": _signature(lines, node.lineno),
                "container": container,
            }
            _append(out, symbol)
            child_container = node.name if kind in {"class", "method"} else container
            for child in getattr(node, "body", []):
                visit(child, child_container)
            return
        for child in ast.iter_child_nodes(node):
            visit(child, container)

    visit(tree)


def _regex_python_symbols(path: str, text: str) -> list[dict]:
    """AST 解析失败时按行匹配 def/class，至少保证名字能搜到。"""
    out: list[dict] = []
    lines = text.splitlines()
    for index, line in enumerate(lines, start=1):
        match = _PY_DEF_RE.match(line)
        if not match:
            continue
        name = match.group(1)
        kind = (
            "class"
            if line.lstrip().startswith(("class ", "async class "))
            else "function"
        )
        _append(
            out,
            {
                "name": name,
                "kind": kind,
                "line": index,
                "end_line": index,
                "signature": line.strip(),
                "container": "",
            },
        )
    return out


def _generic_symbols(path: str, text: str) -> list[dict]:
    """非 Python 文件用通用正则抽顶层声明，够用于定位文件与行号。"""
    out: list[dict] = []
    for index, line in enumerate(text.splitlines(), start=1):
        match = _GENERIC_DEF_RE.match(line)
        if not match:
            continue
        keyword = line.strip().split()[0]
        kind = (
            "class" if keyword in {"class", "interface", "type", "enum"} else "function"
        )
        _append(
            out,
            {
                "name": match.group(1),
                "kind": kind,
                "line": index,
                "end_line": index,
                "signature": line.strip()[:240],
                "container": "",
            },
        )
    return out


def _append(out: list[dict], symbol: dict) -> None:
    """去重：同名同 kind 同行只保留一条。"""
    key = (symbol["name"], symbol["kind"], symbol["line"])
    if any((item["name"], item["kind"], item["line"]) == key for item in out):
        return
    out.append(symbol)


def _signature(lines: list[str], lineno: int) -> str:
    """取定义首行，最多 240 字符，供搜索结果直接展示。"""
    if 1 <= lineno <= len(lines):
        return lines[lineno - 1].strip()[:240]
    return ""
