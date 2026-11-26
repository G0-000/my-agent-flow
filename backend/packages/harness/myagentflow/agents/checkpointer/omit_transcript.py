"""一、文件说明
    检查点写入前剥离对话记录（messages / ui_messages）。
    为什么这么做：会话历史的事实源是 chat_messages 表，检查点只负责「恢复到哪个 superstep」。
    每轮都把完整 messages 写进检查点，库会随对话线性膨胀，同一份数据两处存也迟早不一致。
    例外：还有未完成的 tool_call（工具执行到一半、等人审批）时必须保留，
    否则 LangGraph 恢复时看不到「AIMessage 带 tool_calls、缺 ToolMessage」这个形状。

二、目录结构
    packages/harness/myagentflow/agents/checkpointer/
    ├── __init__.py  检查点层：对外只暴露「拿 saver / 重置 / 一次性上下文」三件事。
    ├── omit_transcript.py  ← 本文件：写入前剥对话、未完成 tool_call 例外
    ├── provider.py  检查点提供者：单例 + 一次性上下文（memory / sqlite / postgres）。
    └── thread_state_reader.py  只读检查点读线程状态：不编译图。

三、关键方法
    omit_transcript_on_checkpoint_put_enabled()  开关：MYAF_CHECKPOINT_OMIT_TRANSCRIPT，默认开。
    has_unresolved_tool_calls()                  是否有 AI tool_call 还没配对的 ToolMessage。
    omit_transcript_channels()                   安全时清空两个对话通道，返回新 dict。
    OmitTranscriptCheckpointer                   包在真 saver 外面，只改 put/aput，其余透传。
"""
from __future__ import annotations

import os
from typing import Any

from langgraph.checkpoint.base import BaseCheckpointSaver

# 要剥离的两个通道：messages 给模型/工具用，ui_messages 给前端投影用，都不是检查点该存的
_TRANSCRIPT_CHANNELS = ("messages", "ui_messages")

# 关掉开关的写法：0 / false / no / off（大小写不敏感）
_FALSE_VALUES = {"0", "false", "no", "off"}


def omit_transcript_on_checkpoint_put_enabled() -> bool:
    """开关：MYAF_CHECKPOINT_OMIT_TRANSCRIPT，默认开。"""
    raw = (os.getenv("MYAF_CHECKPOINT_OMIT_TRANSCRIPT") or "1").strip().lower()
    return raw not in _FALSE_VALUES


def _tool_call_id(tc: Any) -> str:
    """从 tool_call 里取 id：dict 与对象两种形状都认。"""
    if isinstance(tc, dict):
        return str(tc.get("id") or tc.get("tool_call_id") or "").strip()
    return str(getattr(tc, "id", None) or getattr(tc, "tool_call_id", None) or "").strip()


def _message_type_name(msg: Any) -> str:
    """把消息归一成 ai / tool / 其他：LangChain 对象与 dict 两种形状都认。"""
    if isinstance(msg, dict):
        t = str(msg.get("type") or msg.get("role") or "").strip().lower()
        if t in {"ai", "assistant"}:
            return "ai"
        if t == "tool":
            return "tool"
        return t
    name = type(msg).__name__.lower()
    if "ai" in name:
        return "ai"
    if "tool" in name:
        return "tool"
    return name


def has_unresolved_tool_calls(messages: Any) -> bool:
    """有 AI tool_call 没配对的 ToolMessage 时返回 True（中断/工具中途）。

    做法：扫一遍，AI 的 tool_call id 进集合，ToolMessage 的 tool_call_id 出集合；
    最后集合非空就是「还欠一个工具结果」。
    """
    if not isinstance(messages, list) or not messages:
        return False

    pending: set[str] = set()
    for msg in messages:
        kind = _message_type_name(msg)
        if kind == "ai":
            if isinstance(msg, dict):
                raw_tcs = msg.get("tool_calls")
                if raw_tcs is None and isinstance(msg.get("kwargs"), dict):
                    raw_tcs = msg["kwargs"].get("tool_calls")
            else:
                raw_tcs = getattr(msg, "tool_calls", None)
            for tc in raw_tcs or []:
                tid = _tool_call_id(tc)
                if tid:
                    pending.add(tid)
        elif kind == "tool":
            if isinstance(msg, dict):
                tid = str(msg.get("tool_call_id") or "").strip()
                if not tid and isinstance(msg.get("kwargs"), dict):
                    tid = str(msg["kwargs"].get("tool_call_id") or "").strip()
            else:
                tid = str(getattr(msg, "tool_call_id", None) or "").strip()
            if tid:
                pending.discard(tid)
    return bool(pending)


def omit_transcript_channels(checkpoint: dict[str, Any]) -> dict[str, Any]:
    """安全时清空 messages / ui_messages，返回浅拷贝；不安全或没东西可剥就原样返回。

    返回新 dict 而不是原地改：checkpoint 可能还被调用方持有，原地改会污染它的状态。
    """
    if not isinstance(checkpoint, dict):
        return checkpoint

    channel_values = checkpoint.get("channel_values")
    if not isinstance(channel_values, dict):
        return checkpoint

    messages = channel_values.get("messages")
    if has_unresolved_tool_calls(messages):
        return checkpoint

    # 没有对话也没有 UI 消息：不用白拷一份
    if not messages and not channel_values.get("ui_messages"):
        return checkpoint

    new_values = dict(channel_values)
    new_values["messages"] = []
    if "ui_messages" in new_values:
        new_values["ui_messages"] = []
    out = dict(checkpoint)
    out["channel_values"] = new_values
    return out


class OmitTranscriptCheckpointer(BaseCheckpointSaver[Any]):
    """包在真 saver 外面：put/aput 前剥对话，其余方法显式透传。

    LangGraph 现在用 isinstance 校验 checkpointer，单纯 __getattr__ 转发不够；
    必须继承 BaseCheckpointSaver，并把读写方法显式挂到类上。
    """

    def __init__(self, inner: Any) -> None:
        super().__init__(serde=getattr(inner, "serde", None))
        self._inner = inner

    @property
    def config_specs(self) -> list:
        return getattr(self._inner, "config_specs", [])

    def get_tuple(self, *args: Any, **kwargs: Any) -> Any:
        return self._inner.get_tuple(*args, **kwargs)

    def list(self, *args: Any, **kwargs: Any) -> Any:
        return self._inner.list(*args, **kwargs)

    def get_next_version(self, *args: Any, **kwargs: Any) -> Any:
        return self._inner.get_next_version(*args, **kwargs)

    def put_writes(self, *args: Any, **kwargs: Any) -> Any:
        return self._inner.put_writes(*args, **kwargs)

    def delete_thread(self, *args: Any, **kwargs: Any) -> Any:
        return self._inner.delete_thread(*args, **kwargs)

    def delete_for_runs(self, *args: Any, **kwargs: Any) -> Any:
        return self._inner.delete_for_runs(*args, **kwargs)

    def copy_thread(self, *args: Any, **kwargs: Any) -> Any:
        return self._inner.copy_thread(*args, **kwargs)

    def prune(self, *args: Any, **kwargs: Any) -> Any:
        return self._inner.prune(*args, **kwargs)

    async def aget_tuple(self, *args: Any, **kwargs: Any) -> Any:
        return await self._inner.aget_tuple(*args, **kwargs)

    async def alist(self, *args: Any, **kwargs: Any) -> Any:
        return await self._inner.alist(*args, **kwargs)

    async def aput_writes(self, *args: Any, **kwargs: Any) -> Any:
        return await self._inner.aput_writes(*args, **kwargs)

    async def adelete_thread(self, *args: Any, **kwargs: Any) -> Any:
        return await self._inner.adelete_thread(*args, **kwargs)

    async def adelete_for_runs(self, *args: Any, **kwargs: Any) -> Any:
        return await self._inner.adelete_for_runs(*args, **kwargs)

    async def acopy_thread(self, *args: Any, **kwargs: Any) -> Any:
        return await self._inner.acopy_thread(*args, **kwargs)

    async def aprune(self, *args: Any, **kwargs: Any) -> Any:
        return await self._inner.aprune(*args, **kwargs)

    def put(self, config: Any, checkpoint: Any, metadata: Any, new_versions: Any) -> Any:
        """写检查点前剥对话；开关关闭时原样写。"""
        if omit_transcript_on_checkpoint_put_enabled() and isinstance(checkpoint, dict):
            checkpoint = omit_transcript_channels(checkpoint)
        return self._inner.put(config, checkpoint, metadata, new_versions)

    async def aput(self, config: Any, checkpoint: Any, metadata: Any, new_versions: Any) -> Any:
        """异步写入口，规则与 put 相同。"""
        if omit_transcript_on_checkpoint_put_enabled() and isinstance(checkpoint, dict):
            checkpoint = omit_transcript_channels(checkpoint)
        return await self._inner.aput(config, checkpoint, metadata, new_versions)

# =============================================================================
# 说明：这个文件到底在干什么（读代码前先看这一段）
# =============================================================================
#
# 一句话
# -----------------------------------------------------------------------------
# 在把「存档点」写进数据库之前，先把存档点里的聊天记录清空；
# 但如果工具调用还没跑完，就必须保留聊天记录。
#
# 它拦在哪
# -----------------------------------------------------------------------------
#   LangGraph 执行一步
#      ↓ 要保存状态
#   get_checkpointer() 返回的 saver
#      ↓ 外面其实包了一层 OmitTranscriptCheckpointer
#   put(config, checkpoint, ...)
#      ↓ 先判断：能不能剥？有没有没跑完的工具？
#      ↓ 能剥 → messages / ui_messages 置空
#      ↓
#   真正的 SqliteSaver / InMemorySaver 落库
#
# LangGraph 每一步都会把当前 state 写进 checkpoint。这个 wrapper 在真正写入
# 之前插一脚，把「对话记录」换成一个空列表。
#
# 为什么要这么做
# -----------------------------------------------------------------------------
# 一个 checkpoint 大概长这样：
#
#   {
#     "channel_values": {
#       "messages": [
#         {"type": "human", "content": "你好"},
#         {"type": "ai", "content": "在的"}
#       ],
#       "ui_messages": [{"type": "human"}],
#       "plan": {"step": 1}
#     }
#   }
#
# 如果每轮都原样写：
#   1. 第 1 轮存 2 条消息，第 2 轮存 4 条，第 10 轮存 20 条……存档点越来越大；
#   2. 同一份聊天记录在 chat_messages 表和 checkpoint 里各存一份，迟早不一致；
#   3. checkpoint 的职责只是「恢复到第几步、各通道的值是什么」，
#      不该替消息表保管整段对白。
#
# 所以正常轮次写库前会变成：
#
#   {
#     "channel_values": {
#       "messages": [],
#       "ui_messages": [],
#       "plan": {"step": 1}
#     }
#   }
#
# 注意：plan 等其他通道原样保留，只有 messages / ui_messages 被清空。
#
# 什么时候不能清空
# -----------------------------------------------------------------------------
# 工具调用到一半时，必须保留。
#
#   HumanMessage("帮我查天气")
#   AIMessage(tool_calls=[{id: "call-1", name: "weather"}])
#   （还没有 ToolMessage）
#
# 这时 has_unresolved_tool_calls() 会扫一遍：
#   1. AI 消息里的 tool_call id 放进集合 → {"call-1"}
#   2. ToolMessage 的 tool_call_id 从集合移除
#   3. 最后集合非空 → 说明「还欠一个工具结果」
#
# 为什么必须保留：LangGraph 恢复时要看到「AI 说要调 call-1、但还没有对应
# ToolMessage」这个形状，才能继续执行工具。清空后恢复时找不到这个调用，
# 状态链会断。
#
# 等 ToolMessage 回来：
#   AIMessage(tool_calls=["call-1"])
#   ToolMessage(tool_call_id="call-1")
# 集合变成空，说明这一轮工具跑完了，下一次写存档就可以正常清空。
#
# 三个关键函数
# -----------------------------------------------------------------------------
# omit_transcript_on_checkpoint_put_enabled()
#   读环境变量 MYAF_CHECKPOINT_OMIT_TRANSCRIPT，默认开；
#   写 0 / false / no / off 关闭。每次 put 都重新读，运行中也能改。
#
# has_unresolved_tool_calls(messages)
#   扫消息，判断是否还有 AI tool_call 没有配对的 ToolMessage。
#
# omit_transcript_channels(checkpoint)
#   安全时返回一个新 dict，把 messages、ui_messages 置空；
#   不安全（有未完成工具）时原样返回原对象。
#
# OmitTranscriptCheckpointer 是包装器：
#   - put() / aput()：真正做剥离的两个写入口；
#   - __getattr__：其他方法直接转给真 saver；
#   - delete_thread / alist / aput_writes 显式写出来，是因为 LangGraph 会检查
#     「这个 saver 支持哪些能力」，只靠 __getattr__ 可能探测不到。
#
# 另外，返回新 dict 而不是改原对象：checkpoint 可能还被调用方持有，
# 原地改会污染调用方看到的状态。
#
# 它不做什么
# -----------------------------------------------------------------------------
#   - 不删除 chat_messages 表里的消息；
#   - 不删除已经写过的旧 checkpoint；
#   - 不负责把历史读回来；
#   - 不是「清理磁盘」「压缩数据库」的工具。
#
# 它只影响「这一次即将写入的 checkpoint 内容」。
#
# 当前项目的真实情况（最容易误解的地方）
# -----------------------------------------------------------------------------
# 这个文件目前还没有真正作用到你的对话上：
#
#   1. cli/main.py 里的 build_graph(create_chat_model()) 没有传 checkpointer；
#   2. 目前只有显式调用 get_checkpointer() 的地方，才会拿到包装后的 saver；
#   3. 项目里也还没有「从 chat_messages 读回历史、再塞进 messages 后调用图」
#      的 hydrate 流程。
#
# 所以：
#   - 现在它更像「为后续接入准备好的存储层」；
#   - 一旦把 checkpointer 接到图上、又没有 hydrate，默认开启剥离会导致多轮
#     对话丢上下文——因为图靠 checkpoint 里的 messages 记历史；
#   - 正确顺序是：调用前从消息表读出历史 → 用历史 + 新消息调图 →
#     写 checkpoint 时再剥离；或者接入前先把
#     MYAF_CHECKPOINT_OMIT_TRANSCRIPT=0 关掉。
#
# 怎么自己验证
# -----------------------------------------------------------------------------
#   cd /Users/main/my-agent-flow/backend
#   uv run pytest tests/chapters/test_ch02_01_checkpointer.py -q
#   期望：5 passed
#
# 三个剥离用例分别覆盖：
#   1. 正常轮次：messages / ui_messages 被清空，plan 不动；
#   2. 工具未完成：messages 原样保留；
#   3. 开关关闭：什么都不改。
