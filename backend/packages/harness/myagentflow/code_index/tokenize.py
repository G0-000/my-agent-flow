"""一、文件说明
    代码检索用的轻量分词：拆 CamelCase/snake_case，抽标识符与中文二元组，拼 FTS 辅助文本。
    为什么不用语言分词器：代码检索要先保证「符号名精确命中」，分词只服务于兜底全文检索。

二、目录结构
    packages/harness/myagentflow/code_index/
    ├── __init__.py
    ├── tokenize.py  ← 本文件
    ├── symbols.py  符号抽取
    ├── import_bindings.py  import 别名
    ├── internal_refs.py  内部调用引用
    ├── store.py  索引与查询
    └── format_results.py  结果转文本

三、关键方法
    split_identifier()    把 HTTPServer 拆成 HTTP/Server。
    tokens_from_text()    代码文本 → 去重 token 列表。
    build_fts_aux_text()  生成 FTS 辅助文本，提升全文召回。
"""

from __future__ import annotations

import re

_IDENTIFIER_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]{1,}")
_CJK_RE = re.compile(r"[\u4e00-\u9fff]{2,}")
_CAMEL_RE = re.compile(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")
_STOPWORDS = {
    "def",
    "class",
    "return",
    "import",
    "from",
    "self",
    "none",
    "true",
    "false",
    "async",
    "await",
    "function",
    "const",
    "let",
    "var",
}


def split_identifier(identifier: str) -> list[str]:
    """把 ``HTTPServer`` / ``snake_case`` 拆成可检索片段。"""
    raw = str(identifier or "").strip()
    if not raw:
        return []
    pieces = [piece for piece in re.split(r"[_\W]+", raw) if piece]
    out: list[str] = []
    for piece in pieces:
        out.append(piece)
        out.extend(part for part in _CAMEL_RE.sub(" ", piece).split() if part)
    return out


def tokens_from_text(text: str, *, max_tokens: int = 400) -> list[str]:
    """从代码文本抽 token；标识符拆词、中文取二元组，去重后截断。"""
    seen: set[str] = set()
    out: list[str] = []

    def add(token: str) -> None:
        key = token.casefold()
        if len(key) < 2 or key in _STOPWORDS or key in seen:
            return
        seen.add(key)
        out.append(token)

    raw = str(text or "")
    for match in _IDENTIFIER_RE.finditer(raw):
        for piece in split_identifier(match.group(0)):
            add(piece)
    for match in _CJK_RE.finditer(raw):
        run = match.group(0)
        add(run)
        for index in range(len(run) - 1):
            add(run[index : index + 2])
    return out[:max_tokens]


def build_fts_aux_text(
    *, path: str, symbols: list[dict], text: str = "", max_chars: int = 20000
) -> str:
    """拼 FTS 文本：路径 + 符号名 + 源码，符号权重靠前。"""
    parts: list[str] = [str(path or "")]
    for symbol in symbols:
        name = str(symbol.get("name") or "").strip()
        if name:
            parts.append(name)
    if text:
        parts.append(text[:max_chars])
    return "\n".join(parts)
