"""生成对照台账：EvoFlow 有、我们有没有。

为什么用脚本而不是手写：手写台账一定会过期，
这类事实必须每次从代码树重新算。
"""
from __future__ import annotations

import sys
from pathlib import Path


def scan(root: Path) -> dict[str, int]:
    """返回 包名 → 该包下 .py 文件数（不含 __init__.py）。"""
    out: dict[str, int] = {}
    if not root.exists():
        return out
    for pkg in sorted(root.iterdir()):
        if not pkg.is_dir() or pkg.name.startswith("__"):
            continue
        files = [p for p in pkg.rglob("*.py") if p.name != "__init__.py"]
        out[pkg.name] = len(files)
    return out


def classify(ref: int, ours: int) -> str:
    """三态：EvoFlow 有、我们一个源文件都没有 → 空壳；实现了六成以上 → 已实现。"""
    if ref == 0:
        return "新增"          # 只我们有
    if ours == 0:
        return "空壳"          # 目录在、没有实现
    if ours / ref >= 0.6:
        return "已实现"
    return "部分"


def main(evo_root: str, my_root: str) -> int:
    ref = scan(Path(evo_root))
    ours = scan(Path(my_root))
    print("| 模块 | EvoFlow 文件数 | 我们 | 状态 |")
    print("|---|---|---|---|")
    for name in sorted(set(ref) | set(ours)):
        print(f"| {name} | {ref.get(name, 0)} | {ours.get(name, 0)} | {classify(ref.get(name, 0), ours.get(name, 0))} |")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1], sys.argv[2]))
