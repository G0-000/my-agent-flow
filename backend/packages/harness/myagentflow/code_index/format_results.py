"""一、文件说明
    把 search_index 的结构化结果转成给模型看的短文本：路径:行 + 符号 + 片段 + 谁在调用。
    为什么单独格式化：工具层不应该重复拼字符串，也方便测试固定输出顺序。

二、目录结构
    packages/harness/myagentflow/code_index/
    ├── __init__.py
    ├── tokenize.py  轻量分词
    ├── symbols.py  符号抽取
    ├── import_bindings.py  import 别名
    ├── internal_refs.py  内部调用引用
    ├── store.py  索引与查询
    └── format_results.py  ← 本文件

三、关键方法
    format_search_index_body()  结果 → Markdown 风格正文。
"""

from __future__ import annotations

from typing import Any


def format_search_index_body(payload: dict[str, Any]) -> str:
    """把命中列表与引用列表拼成可读正文；没有结果时明确写出。"""
    hits = list(payload.get("hits") or [])
    refs = list(payload.get("internal_ref_users") or [])
    if not hits and not refs:
        query = str(payload.get("query") or "").strip()
        return f"没有找到与 `{query}` 相关的代码结果。"

    lines: list[str] = []
    for hit in hits:
        path = str(hit.get("path") or "")
        line = int(hit.get("line") or 0)
        kind = str(hit.get("kind") or "")
        if kind == "symbol":
            name = str(hit.get("name") or "")
            signature = str(hit.get("signature") or "").strip()
            lines.append(
                f"- `{path}:{line}` · {hit.get('symbolKind') or 'symbol'} `{name}`"
            )
            if signature:
                lines.append(f"  `{signature}`")
        elif kind == "content":
            snippet = str(hit.get("snippet") or "").strip()
            lines.append(f"- `{path}:{line}` · {snippet}")

    if refs:
        lines.append("")
        lines.append("内部引用：")
        for ref in refs:
            lines.append(
                f"- `{ref.get('fromPath')}:{ref.get('line')}` 调用 `{ref.get('symbol')}` "
                f"→ `{ref.get('toPath')}`"
            )
    return "\n".join(lines).strip()
