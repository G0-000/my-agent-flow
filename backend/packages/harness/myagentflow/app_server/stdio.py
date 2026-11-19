"""一、文件说明
    stdio app server：把 Agent 暴露成一个「一行请求、一行响应」的子进程。
    给谁用：桌面端、编辑器插件、脚本 spawn 本进程，通过 stdin/stdout 通信。
    为什么用 JSONL 而不是 HTTP：
      1) 宿主拉起子进程时没有端口可用，也不该为了本地通信去占端口；
      2) 父子进程生命周期天然绑定：父进程关管道，子进程读到 EOF 就退出；
      3) 一根管道只连一个父进程，不会出现多客户端串消息。
    纪律：stdout 只许写协议 JSON；日志、调试输出一律走 stderr。
          混进一行 print()，宿主就会解析失败。

    当前能力边界（别误解）：
      - 已实现：ping 握手、state 读线程检查点。
      - 未实现：chat/send、chat/event、chat/resume、chat/cancel 等流式对话协议；
        也还没有并发、鉴权、TCP 监听。真正的聊天入口在后续 Gateway 章节。

二、目录结构
    packages/harness/myagentflow/app_server/
    ├── __init__.py  包入口（当前为空）。
    └── stdio.py  ← 本文件：JSONL 传输 + 方法分发。

三、关键方法
    handle()  处理一行请求：ping 握手、state 读线程状态；未知方法回 error。
    serve()   从 stdin 逐行读 JSON、调用 handle、把响应写回 stdout；
              坏行只回错误，不退出进程。
    <module>  被 `python -m myagentflow.app_server.stdio` 执行时，__main__ 调 serve()。

四、协议速查
    请求：{"id": 1, "method": "ping"}
    响应：{"id": 1, "result": "pong"}

    请求：{"id": 2, "method": "state", "params": {"thread_id": "t1"}}
    响应：{"id": 2, "result": {...检查点快照...}}  或  {"id": 2, "result": null}

    未知方法：{"id": 3, "error": "未知方法：xxx"}
    坏 JSON：  {"id": null, "error": "Expecting value: ..."}

    注意：这不是完整 JSON-RPC 2.0 —— 没有 "jsonrpc": "2.0" 字段，
    error 也只是字符串，不是 {code, message} 对象。接正式宿主前要补齐。
"""
from __future__ import annotations

import json
import sys
from typing import Any


def handle(req: dict[str, Any]) -> dict[str, Any]:
    """处理一行 JSON-RPC 风格请求，返回一行响应。

    Args:
        req: 已经 json.loads 过的请求对象；不保证字段齐全。

    Returns:
        可直接 json.dumps 的响应 dict：
          - 成功：{"id": ..., "result": ...}
          - 失败：{"id": ..., "error": "..."}

    只做分发，不在这里读 stdin / 写 stdout：方便测试直接传 dict。
    """
    method = req.get("method")
    req_id = req.get("id")       # 原样带回，宿主靠它把响应和请求对上

    # 握手：宿主 spawn 子进程后先发这个，收到 pong 才认为 Agent 就绪。
    # 不加载模型、不连数据库，保证冷启动也很快。
    if method == "ping":
        return {"id": req_id, "result": "pong"}

    # 读线程状态：只读检查点，不编译图、不调模型。
    if method == "state":
        # 懒加载：只发 ping 的宿主不该被迫初始化数据库连接。
        # 放在函数内 import，模块被导入时就不会触发 AppConfig / sqlite 初始化。
        from myagentflow.agents.checkpointer import get_checkpointer
        from myagentflow.agents.checkpointer.thread_state_reader import (
            read_thread_state,
        )

        # params 允许缺省；thread_id 与 thread 两种写法都认，方便不同宿主。
        # 都没给时落到 "cli"，和 CLI 的默认线程名保持一致。
        params = req.get("params") or {}
        thread_id = str(params.get("thread_id") or params.get("thread") or "cli")

        # 返回 None 表示该线程没有检查点；这是正常结果，不是错误。
        return {"id": req_id, "result": read_thread_state(get_checkpointer(), thread_id)}

    # 未知方法：明确拒绝，不猜、不暴露内部方法清单。
    # 不返回 result=None，避免宿主把「方法不存在」误判成「执行成功但没结果」。
    return {"id": req_id, "error": f"未知方法：{method}"}


def serve(stdin=sys.stdin, stdout=sys.stdout) -> None:
    """从 stdin 逐行读 JSON 请求，处理完写一行 JSON 到 stdout。

    Args:
        stdin:  可迭代的文本流；默认进程标准输入。
        stdout: 可写的文本流；默认进程标准输出。
                参数化是为了测试能传 io.StringIO，不用真的开子进程。

    循环直到 EOF（父进程关闭管道）才返回；单行出错不终止进程。
    """
    for line in stdin:                 # 阻塞读；EOF 时循环自然结束，进程退出
        line = line.strip()
        if not line:                   # 空行不是请求，直接跳过
            continue

        try:
            resp = handle(json.loads(line))
        except Exception as exc:
            # 两种情况会到这里：
            #   1) 行不是合法 JSON —— 连 id 都拿不到，只能回 id=None；
            #   2) handle() 内部抛出未预期异常。
            # 都不能让进程退出：宿主可能只是某一行写错了。
            resp = {"id": None, "error": str(exc)}

        # ensure_ascii=False：中文原样输出，不转成 \uXXXX，方便人看日志。
        # 末尾换行是消息边界：宿主按行拆 JSON。
        stdout.write(json.dumps(resp, ensure_ascii=False) + "\n")
        # 必须 flush：否则响应可能卡在缓冲区，父进程一直等，表现为「服务卡死」。
        stdout.flush()


# 只有被 `python -m myagentflow.app_server.stdio` 直接执行时才启动循环；
# 被其它模块 import 时不会自动读 stdin，避免测试/宿主进程被意外阻塞。
if __name__ == "__main__":
    serve()


# =============================================================================
# 设计说明（读代码之外，理解这个文件为什么长这样）
# =============================================================================
#
# 1. 它和 cli/main.py 是什么关系
# -----------------------------------------------------------------------------
#   两个都是入口，但服务对象不同：
#     cli/main.py      → 给人用：命令行参数进，终端打印出；
#     app_server/stdio.py → 给程序用：stdin 的 JSON 进，stdout 的 JSON 出。
#   两者互不 import；可以同时作为两个独立进程运行，互不影响。
#
#   如果硬把 serve() 和 CLI 放进同一个进程开线程，会共享全局状态：
#     - provider 的 checkpointer 单例、SQLite 连接；
#     - os.environ；
#     - sys.stdout —— CLI 的 print() 会混进 stdio 协议，宿主直接解析失败。
#   所以正式用法是「分开进程」，不是「同进程开线程」。
#
# 2. 为什么只有 ping / state
# -----------------------------------------------------------------------------
#   本章只验证「子进程 + 管道 + 一行一答」这条链路能通。
#   chat 需要流式事件、取消、断线续传、并发 run 管理，属于后续 Gateway /
#   桌面端章节；现在硬造一套简化协议，后面一定和正式协议不一致。
#
# 3. 为什么错误也走 stdout，而不是抛异常/写 stderr
# -----------------------------------------------------------------------------
#   对宿主来说，「请求失败」也是协议的一部分：它需要知道哪条请求失败了、
#   为什么失败。抛异常会让父进程只看到进程退出；写 stderr 则无法和请求 id
#   对应。所以错误统一包成 {"id", "error"} 从 stdout 回去。
#   真正的日志/堆栈仍应走 stderr，二者不要混。
#
# 4. 已知限制
# -----------------------------------------------------------------------------
#   - 单线程顺序处理：一条请求处理完才读下一行，没有并发；
#   - 没有请求超时：handle 卡住，整个管道就卡住；
#   - 没有鉴权：能启动这个子进程的父进程就能调用；
#   - 没有协议版本协商；
#   - 只支持本机父子进程，不能远程访问。
#
# 5. 最小实测
# -----------------------------------------------------------------------------
#   cd /Users/main/my-agent-flow/backend
#   printf '{"id":1,"method":"ping"}\n{"id":2,"method":"state"}\nnot-json\n' \
#     | uv run python -m myagentflow.app_server.stdio
#
#   期望三行：
#     {"id": 1, "result": "pong"}
#     {"id": 2, "result": null}
#     {"id": null, "error": "Expecting value: line 1 column 1 (char 0)"}
#   且进程退出码为 0 —— 坏行没有拖垮服务。
#
# 6. 对应测试
# -----------------------------------------------------------------------------
#   uv run pytest tests/chapters/test_ch02_03_cli_stdio.py -q
#   覆盖：ping、state、未知方法、坏行恢复、CLI state 输出。
