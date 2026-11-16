"""最小 MCP 客户端：stdio + JSON-RPC。

为什么先只做 stdio：HTTP/SSE 传输要多处理一层鉴权与重连，
stdio 能把「协议本身」讲清楚。
"""
from __future__ import annotations

import json
import subprocess
from typing import Any


class McpClient:
    def __init__(self, command: list[str]) -> None:
        self._proc = subprocess.Popen(
            command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, bufsize=1
        )
        self._id = 0

    def _request(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        self._id += 1
        payload = {"jsonrpc": "2.0", "id": self._id, "method": method, "params": params or {}}
        assert self._proc.stdin and self._proc.stdout
        self._proc.stdin.write(json.dumps(payload) + "\n")
        self._proc.stdin.flush()
        line = self._proc.stdout.readline()
        if not line:
            raise RuntimeError(f"MCP 服务无响应：{method}")
        resp = json.loads(line)
        if "error" in resp:
            raise RuntimeError(f"MCP 错误 {resp['error'].get('code')}: {resp['error'].get('message')}")
        return resp.get("result", {})

    def initialize(self) -> dict[str, Any]:
        return self._request("initialize", {"protocolVersion": "2024-11-05", "capabilities": {}})

    def list_tools(self) -> list[dict[str, Any]]:
        return self._request("tools/list").get("tools", [])

    def call_tool(self, name: str, args: dict[str, Any]) -> Any:
        return self._request("tools/call", {"name": name, "arguments": args})

    def close(self) -> None:
        self._proc.terminate()
