"""stdio app server：一行请求、一行响应。

为什么用 JSONL 而不是 HTTP：桌面端/编辑器插件拉起子进程时没有端口可用，
stdin/stdout 是最稳的通道。
"""
from __future__ import annotations

import json
import sys
from typing import Any


def handle(req: dict[str, Any]) -> dict[str, Any]:
    if req.get("method") != "ping":
        return {"id": req.get("id"), "error": f"未知方法：{req.get('method')}"}
    return {"id": req.get("id"), "result": "pong"}


def serve(stdin=sys.stdin, stdout=sys.stdout) -> None:
    for line in stdin:
        line = line.strip()
        if not line:
            continue
        try:
            resp = handle(json.loads(line))
        except Exception as exc:
            resp = {"id": None, "error": str(exc)}
        stdout.write(json.dumps(resp, ensure_ascii=False) + "\n")
        stdout.flush()   # 不 flush 的话父进程会一直等
