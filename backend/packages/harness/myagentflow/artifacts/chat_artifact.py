"""一、文件说明
    会话产物契约：工具返回的文件/图片/视频/链接/HTML/文本，统一成 ChatArtifact dict。
    为什么要有契约：不同工具返回结构五花八门，前端只认一种形状；
    这里做归一化 + 稳定 id（同一路径/URL 重复出现不新增）。

二、目录结构
    packages/harness/myagentflow/artifacts/
    ├── __init__.py
    └── chat_artifact.py ← 本文件

三、关键方法
    normalize_artifact_type()   类型推断（扩展名 / mime / 别名）。
    make_artifact_id()          稳定主键：path > url > content 哈希。
    normalize_chat_artifact()   单条归一化，非法返回 None。
    normalize_chat_artifacts()  批量 + 去重 + 上限。
    artifact_state_key()        ThreadState 里存字符串键。
"""

from __future__ import annotations

import hashlib
import re
from typing import Any

ARTIFACT_TYPES = frozenset({"file", "image", "video", "url", "html", "text"})

_IMAGE_EXT = frozenset(
    {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".svg", ".ico"}
)
_VIDEO_EXT = frozenset({".mp4", ".webm", ".mov", ".mkv", ".avi", ".m4v"})
_HTML_EXT = frozenset({".html", ".htm"})

_NAME_MAX = 240
_LABEL_MAX = 200
_PATH_MAX = 2000
_URL_MAX = 4000
_CONTENT_MAX = 200_000
_ID_MAX = 128


def normalize_artifact_type(
    raw: Any, *, path: str = "", url: str = "", mime: str = ""
) -> str:
    """显式 type 优先；其次别名、mime、扩展名；最后有 url 算 url，否则 file。"""
    t = str(raw or "").strip().lower()
    if t in ARTIFACT_TYPES:
        return t
    if t in {"path", "filepath", "doc", "document", "attachment"}:
        return "file"
    if t in {"link", "uri", "href"}:
        return "url"
    if t in {"note", "string", "markdown", "md"}:
        return "text"
    if t in {"webpage", "page"}:
        return "html"
    mime_l = str(mime or "").strip().lower()
    if mime_l.startswith("image/"):
        return "image"
    if mime_l.startswith("video/"):
        return "video"
    if mime_l in {"text/html", "application/xhtml+xml"}:
        return "html"
    probe = (path or url or "").lower().split("?", 1)[0]
    for ext in _IMAGE_EXT:
        if probe.endswith(ext):
            return "image"
    for ext in _VIDEO_EXT:
        if probe.endswith(ext):
            return "video"
    for ext in _HTML_EXT:
        if probe.endswith(ext):
            return "html"
    if str(url or "").strip():
        return "url"
    return "file"


def _basename(path_or_url: str) -> str:
    """取路径/URL 最后一段，兼容反斜杠和结尾斜杠。"""
    s = str(path_or_url or "").replace("\\", "/").rstrip("/")
    if not s:
        return ""
    return s.rsplit("/", 1)[-1] or s


def make_artifact_id(
    *, type_: str, path: str = "", url: str = "", content: str = "", name: str = ""
) -> str:
    """稳定 id：同路径、同 URL 必得同一 id，用于追加/更新而不是重复。"""
    if path:
        key = f"path:{path.replace(chr(92), '/')}"
    elif url:
        key = f"url:{url}"
    elif content:
        digest = hashlib.sha256(content.encode("utf-8", errors="ignore")).hexdigest()[
            :24
        ]
        key = f"content:{type_}:{name or 'untitled'}:{digest}"
    else:
        key = f"empty:{type_}:{name or 'untitled'}"
    if len(key) <= _ID_MAX:
        return key
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:40]
    return f"h:{digest}"


def normalize_chat_artifact(raw: Any) -> dict[str, Any] | None:
    """单条归一化；字符串按 http(s) 当 URL，否则当本地文件。"""
    if raw is None:
        return None
    if isinstance(raw, str):
        s = raw.strip()
        if not s:
            return None
        if re.match(r"^https?://", s, re.IGNORECASE):
            return normalize_chat_artifact({"type": "url", "url": s})
        return normalize_chat_artifact({"type": "file", "path": s})
    if not isinstance(raw, dict):
        return None

    path = str(raw.get("path") or "").strip()[:_PATH_MAX]
    url = str(raw.get("url") or raw.get("href") or raw.get("link") or "").strip()[
        :_URL_MAX
    ]
    content = raw.get("content")
    content_s = "" if content is None else str(content)[:_CONTENT_MAX]
    mime = str(raw.get("mime") or raw.get("mime_type") or "").strip()[:120]
    name = str(raw.get("name") or raw.get("filename") or "").strip()[:_NAME_MAX]
    label = str(raw.get("label") or raw.get("title") or "").strip()[:_LABEL_MAX]
    type_ = normalize_artifact_type(
        raw.get("type") or raw.get("kind"), path=path, url=url, mime=mime
    )

    if not path and not url and not content_s:
        return None
    if not name:
        name = _basename(path or url) or (label if label else type_)

    aid = str(raw.get("id") or raw.get("artifact_id") or "").strip()
    if not aid:
        aid = make_artifact_id(
            type_=type_, path=path, url=url, content=content_s, name=name
        )

    size_raw = raw.get("size")
    size: int | None = None
    if size_raw is not None:
        try:
            size = max(0, int(size_raw))
        except (TypeError, ValueError):
            size = None

    out: dict[str, Any] = {"id": aid[:_ID_MAX], "type": type_, "name": name}
    if path:
        out["path"] = path
    if url:
        out["url"] = url
    if content_s and type_ in {"html", "text"}:
        out["content"] = content_s
    if label:
        out["label"] = label
    if mime:
        out["mime"] = mime
    if size is not None:
        out["size"] = size
    status = str(raw.get("status") or "").strip().lower()
    if status in {"new", "updated"}:
        out["status"] = status
    return out


def normalize_chat_artifacts(raw: Any, *, limit: int = 40) -> list[dict[str, Any]]:
    """批量归一化：id 去重，最多 limit 条。"""
    if raw is None:
        return []
    items: list[Any] = raw if isinstance(raw, list) else [raw]
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for it in items:
        if len(out) >= limit:
            break
        n = normalize_chat_artifact(it)
        if not n:
            continue
        aid = str(n["id"])
        if aid in seen:
            continue
        seen.add(aid)
        out.append(n)
    return out


def artifact_state_key(item: dict[str, Any]) -> str:
    """ThreadState.artifacts 存字符串键：path 优先，其次 url，最后 id。"""
    path = str(item.get("path") or "").strip()
    if path:
        return path
    url = str(item.get("url") or "").strip()
    if url:
        return url
    return str(item.get("id") or "").strip()
