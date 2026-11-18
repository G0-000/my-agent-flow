"""一、文件说明
    批量把模块顶部 docstring 规整成三段：文件说明 / 目录结构 / 关键方法。
    为什么用脚本：90 个模块手写头注释容易漏；脚本只做「结构 + 已有信息搬运」，
    说明文字仍取原 docstring 与函数 docstring，不凭空生成。

二、目录结构
    backend/tools/
    └── file_headers.py   ← 本文件

三、关键方法
    build_header()    为单个文件生成三段式 docstring
    apply_all()       遍历 myagentflow 包并按需改写
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "packages" / "harness" / "myagentflow"


import re

_TREE_LINE = re.compile(r"^[a-z_]+(?:/[a-z0-9_]+)*/?(?:[a-z0-9_]+)?\.py\b")
_SKIP_PREFIX = ("调用方向", "依赖方向", "模块位置", "目录结构", "├", "└", "│")


def _purpose_text(doc: str | None) -> str:
    """取「一、文件说明」段，去掉手画路径树与调用方向行，避免和新目录树重复。"""
    if not doc:
        return ""
    lines = doc.strip().splitlines()
    if any(line.strip() == "一、文件说明" for line in lines):
        start = next(i for i, line in enumerate(lines) if line.strip() == "一、文件说明") + 1
        end = next((i for i, line in enumerate(lines) if line.strip() == "二、目录结构"), len(lines))
        lines = lines[start:end]
    kept = []
    for line in lines:
        text = line.strip()
        if not text:
            continue
        if any(text.startswith(prefix) for prefix in _SKIP_PREFIX):
            continue
        if "← 本文件" in text or _TREE_LINE.match(text):
            continue
        kept.append("    " + line.strip())
    return "\n".join(kept)


def _first_line(doc: str | None) -> str:
    if not doc:
        return ""
    section_marks = ("一、文件说明", "二、目录结构", "三、关键方法")
    for line in doc.strip().splitlines():
        text = line.strip()
        if not text or text in section_marks:
            continue
        return text
    return ""


def _purpose_map(directory: Path) -> dict[str, str]:
    """同目录下每个 .py 的一句话用途，用于目录树右侧说明。"""
    purposes: dict[str, str] = {}
    for py in sorted(directory.glob("*.py")):
        try:
            module = ast.parse(py.read_text(encoding="utf-8"))
        except SyntaxError:
            purposes[py.name] = ""
            continue
        purposes[py.name] = _first_line(ast.get_docstring(module))
    return purposes


def _tree(directory: Path, current: Path) -> str:
    purposes = _purpose_map(directory)
    rel_dir = directory.relative_to(ROOT)
    lines = [f"    {rel_dir}/"]
    files = sorted(purposes.items())
    for index, (name, purpose) in enumerate(files):
        branch = "└──" if index == len(files) - 1 else "├──"
        mark = "  ← 本文件" if name == current.name else ""
        note = f"  {purpose[:40]}" if purpose and name != current.name else ""
        lines.append(f"    {branch} {name}{mark}{note}")
    return "\n".join(lines)


_REF = re.compile(r"（(?:对齐|EvoFlow|参考)[^）]*）")


def _clean(desc: str) -> str:
    """去掉符号说明里的源码出处括注：出处属于文档对照表，不属于代码注释。"""
    return _REF.sub("", desc).strip()


def _symbols(source: str) -> list[tuple[str, str]]:
    """顶层函数/类 + 其 docstring 首行；没有 docstring 就留空，不编。"""
    tree = ast.parse(source)
    out: list[tuple[str, str]] = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            out.append((f"{node.name}()", _clean(_first_line(ast.get_docstring(node)))))
        elif isinstance(node, ast.ClassDef):
            out.append((node.name, _clean(_first_line(ast.get_docstring(node)))))
    return out


def build_header(path: Path) -> str:
    source = path.read_text(encoding="utf-8")
    module = ast.parse(source)
    original = _purpose_text(ast.get_docstring(module)) or "（未写说明：补一句这个文件负责什么）"
    symbols = _symbols(source)

    parts = ["一、文件说明"]
    for line in original.splitlines():
        parts.append("    " + line.strip() if line.strip() else "")
    parts.append("")
    parts.append("二、目录结构")
    parts.append(_tree(path.parent, path))
    parts.append("")
    parts.append("三、关键方法")
    if symbols:
        name_width = max(len(name) for name, _ in symbols)
        for name, desc in symbols:
            parts.append(f"    {name.ljust(name_width)}  {desc}".rstrip())
    else:
        parts.append("    （仅模块级常量，无公开函数）")
    return '"""' + "\n".join(parts) + '\n"""'


def apply_all(parts_filter: str | None = None, force: bool = False) -> tuple[int, int]:
    changed = skipped = 0
    for py in sorted(PKG.rglob("*.py")):
        if "__pycache__" in py.parts or py.stat().st_size == 0:
            skipped += 1
            continue
        if parts_filter and parts_filter not in str(py.relative_to(PKG)):
            continue
        source = py.read_text(encoding="utf-8")
        try:
            module = ast.parse(source)
        except SyntaxError:
            skipped += 1
            continue
        if not force and "三、关键方法" in (ast.get_docstring(module) or ""):
            continue
        header = build_header(py)
        if module.body and isinstance(module.body[0], ast.Expr) and isinstance(module.body[0].value, ast.Constant):
            end_line = module.body[0].end_lineno or 0
            body = source.splitlines()[end_line:]
            new_source = header + "\n" + "\n".join(body).lstrip("\n")
        else:
            new_source = header + "\n" + source
        py.write_text(new_source.rstrip() + "\n", encoding="utf-8")
        changed += 1
    return changed, skipped


if __name__ == "__main__":
    args = sys.argv[1:]
    force = "--force" in args
    target = next((arg for arg in args if not arg.startswith("--")), None)
    changed, skipped = apply_all(target, force=force)
    print(f"changed={changed} skipped={skipped}")
