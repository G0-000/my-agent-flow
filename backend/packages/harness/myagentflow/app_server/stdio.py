"""一、文件说明
    stdio app server：一行请求、一行响应。
    为什么用 JSONL 而不是 HTTP：桌面端/编辑器插件拉起子进程时没有端口可用，
    stdin/stdout 是最稳的通道。

二、目录结构
    packages/harness/myagentflow/app_server/
    ├── __init__.py
    └── stdio.py  ← 本文件

三、关键方法
    handle()  处理一行 JSON-RPC 请求：ping 握手、state 读线程状态；其他方法回错误。
    serve()   从 stdin 逐行读 JSON-RPC 并写回 stdout；坏行返回错误而不退出进程。
"""
from __future__ import annotations

import json
import sys
from typing import Any


def handle(req: dict[str, Any]) -> dict[str, Any]:
    """处理一行 JSON-RPC 请求：ping 握手、state 读线程状态；其他方法回错误。"""
    method = req.get("method")
    req_id = req.get("id")

    if method == "ping":
        return {"id": req_id, "result": "pong"}

    if method == "state":
        # 懒加载：只用 ping 的宿主不该被迫初始化数据库连接
        from myagentflow.agents.checkpointer import get_checkpointer
        from myagentflow.agents.checkpointer.thread_state_reader import (
            read_thread_state,
        )

        params = req.get("params") or {}
        thread_id = str(params.get("thread_id") or params.get("thread") or "cli")
        return {"id": req_id, "result": read_thread_state(get_checkpointer(), thread_id)}

    return {"id": req_id, "error": f"未知方法：{method}"}


def serve(stdin=sys.stdin, stdout=sys.stdout) -> None:
    """从 stdin 逐行读 JSON-RPC 并写回 stdout；坏行返回错误而不退出进程。"""
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


if __name__ == "__main__":
    serve()
