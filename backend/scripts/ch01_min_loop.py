#!/usr/bin/env python3
# 最小演示脚本：读取一行用户输入，调用当前配置的聊天模型完成一次对话，
# 并把输出同时打印到 stdout 与写入 tmp/ch01/output.txt。

from __future__ import annotations

import sys
from pathlib import Path

from langchain_core.messages import HumanMessage

from myagentflow.models.factory import create_chat_model


def main() -> int:
    user = sys.stdin.readline().strip() or "你好"
    model = create_chat_model()
    reply = model.invoke([HumanMessage(content=user)])

    text = getattr(reply, "content", "")
    print(text)

    out_dir = Path(__file__).resolve().parents[1] / "tmp" / "ch01"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "output.txt").write_text(str(text), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
