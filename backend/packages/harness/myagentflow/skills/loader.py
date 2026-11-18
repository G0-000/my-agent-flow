"""一、文件说明
    插件加载：声明式入口 + 失败隔离。
    为什么失败不抛出：插件是第三方代码，一个 import 报错
    不该让整个宿主起不来。

二、目录结构
    packages/harness/myagentflow/skills/
    ├── __init__.py
    ├── loader.py  ← 本文件
    └── registry.py  技能包注册：manifest 校验 + 安装列表。

三、关键方法
    PluginSpec  插件声明：名字与 entry（模块:函数）。
    load()      按 entry 动态导入可调用对象；失败返回 None 并记日志。
    load_all()  批量加载插件，跳过加载失败的项。
"""
from __future__ import annotations

import importlib
import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PluginSpec:
    """插件声明：名字与 entry（模块:函数）。"""
    name: str
    entry: str          # "package.module:function"


def load(spec: PluginSpec) -> Callable[..., Any] | None:
    """按 entry 动态导入可调用对象；失败返回 None 并记日志。"""
    module_name, _, attr = spec.entry.partition(":")
    try:
        module = importlib.import_module(module_name)
        fn = getattr(module, attr)
    except Exception as exc:
        logger.error("插件加载失败 %s：%s", spec.name, exc)
        return None
    return fn

def load_all(specs: list[PluginSpec]) -> dict[str, Callable[..., Any]]:
    """批量加载插件，跳过加载失败的项。"""
    loaded = {}
    for spec in specs:
        fn = load(spec)
        if fn is not None:
            loaded[spec.name] = fn
    return loaded
