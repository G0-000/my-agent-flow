"""知识地图：文档 → 标题 → 块 id。

为什么要地图：让模型先看「有哪些文档」，再决定检索哪一篇，
比直接 top-k 更省 token，也更少答错文档。
"""
from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable


def build_map(items: Iterable[dict]) -> dict[str, dict[str, list[int]]]:
    tree: dict[str, dict[str, list[int]]] = defaultdict(lambda: defaultdict(list))
    for it in items:                       # it: {doc_id, heading, chunk_id}
        tree[it["doc_id"]][it["heading"]].append(it["chunk_id"])
    return {doc: dict(secs) for doc, secs in tree.items()}


def describe(tree: dict[str, dict[str, list[int]]], max_docs: int = 5,
             max_sections: int = 3) -> str:
    lines = []
    for doc, sections in list(tree.items())[:max_docs]:
        count = sum(len(v) for v in sections.values())
        names = list(sections)[:max_sections]
        lines.append(f"- {doc}（{count} 块）：" + "、".join(names))
    return "\n".join(lines)
