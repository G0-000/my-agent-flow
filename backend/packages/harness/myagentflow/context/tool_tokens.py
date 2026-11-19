"""一、文件说明
    工具结果 token 计数：截断、落盘阈值共用同一个估算口径。
    为什么单独一个文件：截断和落盘如果各算各的，阈值会出现「这边说超了、
    那边说没超」的分裂。

二、目录结构
    packages/harness/myagentflow/context/
    ├── __init__.py
    ├── budget.py     上下文预算：阈值、回填
    ├── tool_tokens.py  ← 本文件：工具结果 token 估算
    └── ...

三、关键方法
    count_tool_tokens()  估算工具结果 token 数；当前用 budget.estimate_tokens。
"""
from __future__ import annotations

from myagentflow.context.budget import estimate_tokens

# 兼容 EvoFlow 的字符/token 经验值；本项目的估算在 budget.estimate_tokens 里
_CHARS_PER_TOKEN = 4


def count_tool_tokens(text: str, *, model: str | None = None) -> int:
    """估算工具结果 token 数；当前用 budget.estimate_tokens。"""
    del model  # 当前不按模型路由 tokenizer，先统一口径
    return estimate_tokens(text)
