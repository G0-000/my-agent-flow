"""一、文件说明
    CLI：最小两个子命令。
    为什么 CLI 要和 Gateway 共用代码：调试时想在终端复现线上问题，
    两条代码路径一定会分叉。

二、目录结构
    packages/harness/myagentflow/cli/
    ├── __init__.py
    └── main.py  ← 本文件

三、关键方法
    _chat()
    _state()
    main()
"""
from __future__ import annotations

import argparse
import json

from myagentflow.models.factory import create_chat_model


def _chat(args: argparse.Namespace) -> int:
    from langchain_core.messages import HumanMessage

    from myagentflow.agents.lead_agent.graph import build_graph

    graph = build_graph(create_chat_model())
    out = graph.invoke(
        {"messages": [HumanMessage(content=args.text)]},
        {"configurable": {"thread_id": args.thread}},
    )
    print(out["messages"][-1].content)
    return 0


def _state(args: argparse.Namespace) -> int:
    from myagentflow.agents.checkpointer import get_checkpointer
    from myagentflow.agents.checkpointer.thread_state_reader import read_thread_state

    # 注意：这里绝不导入 build_graph —— 读状态不该编译图
    print(json.dumps(read_thread_state(get_checkpointer(), args.thread), ensure_ascii=False))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="myaf")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_chat = sub.add_parser("chat", help="跑一轮对话")
    p_chat.add_argument("text")
    p_chat.add_argument("--thread", default="cli")
    p_chat.set_defaults(fn=_chat)

    p_state = sub.add_parser("state", help="读线程状态（不编译图）")
    p_state.add_argument("--thread", default="cli")
    p_state.set_defaults(fn=_state)

    args = parser.parse_args(argv)
    return int(args.fn(args))


if __name__ == "__main__":
    raise SystemExit(main())
