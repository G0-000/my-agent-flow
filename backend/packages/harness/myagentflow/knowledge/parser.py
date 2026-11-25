"""一、文件说明
    文档解析：把上传文件转成纯文本，供切块与索引使用。
    本章只做纯文本与 Markdown，以及 docx/pptx 的 stdlib 解包；PDF 依赖可选的 pypdf，
    不把某个转换器写死，避免一个依赖缺失就让整条上传链路不可用。

二、目录结构
    packages/harness/myagentflow/knowledge/
    ├── __init__.py
    ├── parser.py  ← 本文件：文件 → 纯文本
    ├── chunker.py  文本 → 带字符区间的块
    ├── wiki_chunker.py  按标题结构切块
    └── index_builder.py  文档摘要与块索引文本

三、关键方法
    parse_file()          按扩展名读文本或解包 Office 文档；失败时带 doc_id/kb_id 上下文。
    supported_extensions() 返回当前实现能接收的扩展名集合。
"""

from __future__ import annotations

import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree

_TEXT_EXTENSIONS = {
    ".txt",
    ".md",
    ".markdown",
    ".mdx",
    ".csv",
    ".json",
    ".xml",
    ".html",
    ".htm",
    ".log",
    ".yaml",
    ".yml",
    ".toml",
}
_OOXML_EXTENSIONS = {".docx", ".pptx"}
_OPTIONAL_PDF_EXTENSIONS = {".pdf"}
_SUPPORTED_EXTENSIONS = _TEXT_EXTENSIONS | _OOXML_EXTENSIONS | _OPTIONAL_PDF_EXTENSIONS

_PPTX_SLIDE_RE = re.compile(r"^ppt/slides/slide(\d+)\.xml$")
_DRAWINGML_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"


def parse_file(
    file_path: str | Path,
    *,
    doc_id: str | None = None,
    kb_id: str | None = None,
) -> str:
    """把文件解析成纯文本。

    纯文本按 UTF-8 读取；docx/pptx 直接解 zip + XML，不依赖 Office 运行时；
    PDF 有 pypdf 才解析，否则明确报缺少依赖，而不是返回空串。
    """
    p = Path(file_path)
    if not p.exists():
        ctx = _format_context(doc_id=doc_id, kb_id=kb_id, path=p)
        raise FileNotFoundError(f"File not found: {p} ({ctx})")

    ext = p.suffix.lower()
    ctx = _format_context(doc_id=doc_id, kb_id=kb_id, path=p)
    if ext in _TEXT_EXTENSIONS:
        return p.read_text(encoding="utf-8", errors="replace")
    if ext == ".docx":
        return _fallback_docx(p, ctx=ctx)
    if ext == ".pptx":
        return _fallback_pptx(p, ctx=ctx)
    if ext == ".pdf":
        return _parse_pdf(p, ctx=ctx)
    raise ValueError(f"Unsupported file type '{ext}' ({ctx})")


def supported_extensions() -> set[str]:
    """返回当前实现能接收的扩展名集合。"""
    return set(_SUPPORTED_EXTENSIONS)


def _format_context(*, doc_id: str | None, kb_id: str | None, path: Path) -> str:
    """把 doc/kb/path 拼成错误上下文，便于上传失败时定位是哪一个文件。"""
    parts: list[str] = []
    if kb_id:
        parts.append(f"kb_id={kb_id}")
    if doc_id:
        parts.append(f"doc_id={doc_id}")
    parts.append(f"path={path}")
    return ", ".join(parts)


def _parse_pdf(p: Path, *, ctx: str) -> str:
    """用可选依赖 pypdf 提取 PDF 文本；没装时直接说明缺哪个包。"""
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise RuntimeError(f"无法解析 {p.name}：缺少 PDF 依赖 pypdf ({ctx})") from exc
    try:
        reader = PdfReader(str(p))
        pages = [(page.extract_text() or "") for page in reader.pages]
    except Exception as exc:
        raise RuntimeError(f"无法解析 {p.name}：{exc} ({ctx})") from exc
    text = "\n\n".join(page for page in pages if page.strip()).strip()
    if not text:
        raise RuntimeError(
            f"无法解析 {p.name}：PDF 没有可提取文本，可能需要 OCR ({ctx})"
        )
    return text


def _fallback_docx(p: Path, *, ctx: str) -> str:
    """stdlib 读取 docx 的 word/document.xml，只取正文文本。"""
    try:
        with zipfile.ZipFile(p) as archive:
            xml = archive.read("word/document.xml")
        root = ElementTree.fromstring(xml)
    except (KeyError, zipfile.BadZipFile, ElementTree.ParseError) as exc:
        raise RuntimeError(f"无法解析 {p.name}：不是有效的 docx ({ctx})") from exc
    lines = [node.text or "" for node in root.iter() if node.tag.endswith("}t")]
    text = "\n".join(line.strip() for line in lines if line.strip()).strip()
    if not text:
        raise RuntimeError(f"无法解析 {p.name}：docx 没有正文 ({ctx})")
    return text


def _fallback_pptx(p: Path, *, ctx: str) -> str:
    """stdlib 读取 pptx 每页 slide 的 DrawingML 文本，并按页码排序。"""
    slides: list[tuple[int, str]] = []
    try:
        with zipfile.ZipFile(p) as archive:
            for name in archive.namelist():
                match = _PPTX_SLIDE_RE.match(name)
                if not match:
                    continue
                with archive.open(name) as handle:
                    root = ElementTree.parse(handle).getroot()
                texts = [node.text or "" for node in root.iter(f"{{{_DRAWINGML_NS}}}t")]
                body = "\n".join(text.strip() for text in texts if text.strip())
                slides.append((int(match.group(1)), body))
    except (zipfile.BadZipFile, ElementTree.ParseError) as exc:
        raise RuntimeError(f"无法解析 {p.name}：不是有效的 pptx ({ctx})") from exc
    slides.sort()
    parts: list[str] = []
    for number, body in slides:
        parts.append(f"<!-- Slide number: {number} -->")
        if body:
            parts.append(body)
    text = "\n".join(parts).strip()
    if not text:
        raise RuntimeError(f"无法解析 {p.name}：pptx 没有正文 ({ctx})")
    return text
