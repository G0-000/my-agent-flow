"""技能包注册：manifest 校验 + 安装列表。

为什么安装时就校验：坏包在运行时才炸，用户看到的是「Agent 突然不能用了」，
很难联想到是某个技能包的问题。
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

# manifest 的版本号只接受 x.y.z 三段数字：带 v 前缀或日期版本会让排序出错
_VER = re.compile(r"^\d+\.\d+\.\d+$")


@dataclass(frozen=True)
class Manifest:
    name: str
    version: str
    entry: str


def read_manifest(pkg_dir: Path) -> Manifest:
    data = json.loads((pkg_dir / "manifest.json").read_text(encoding="utf-8"))
    for key in ("name", "version", "entry"):
        if not data.get(key):
            raise ValueError(f"manifest 缺少字段：{key}")
    if not _VER.match(data["version"]):
        raise ValueError(f"版本号不合法：{data['version']}（应为 x.y.z）")
    return Manifest(data["name"], data["version"], data["entry"])


class SkillRegistry:
    def __init__(self) -> None:
        self._installed: dict[str, Manifest] = {}

    def install(self, pkg_dir: Path) -> Manifest:
        m = read_manifest(pkg_dir)
        if m.name in self._installed:
            raise ValueError(f"技能已安装：{m.name}（升级请走 upgrade）")
        self._installed[m.name] = m
        return m

    def list(self) -> list[dict]:
        return [{"name": m.name, "version": m.version} for m in self._installed.values()]
