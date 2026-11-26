# my-agent-flow 开发待办（阶段：第 01–05 篇）

目标：与 v2 文档（/Users/main/agent-book/my-agent-flow-v2）对齐，代码跑通第 01–05 篇的最小闭环与章节用例；对应测试全部通过。

路径约定：
- 文档：/Users/main/agent-book/my-agent-flow-v2
- 代码：/Users/main/my-agent-flow/backend
- 参考源码地图：/Users/main/EvoFlow

运行基线：
- Python 3.12
- 在 backend 下运行：
  - 安装：`uv sync`（已配置 workspace: packages/harness）
  - 启动（如需本地 API）：`uv run python -m myagentflow.app_server`（按需）
  - 测试：`uv run pytest -q tests/chapters/test_ch01_*.py`（逐章推进）

验收标准（必须同时满足）：
- 章节级：本阶段相关的 tests/chapters/test_ch01_* ～ test_ch05_* 全部通过。
- 篇级：每篇“篇级最小闭环”能以脚本或 API 复现（见各 README）。
- 安全与边界：危险操作默认拒绝或需审批；宿主边界、路径守卫、超时与预算有效。

---
## 第 01 篇 最小可运行 Agent（ch01_*）
文档：agent-book/my-agent-flow-v2/01-最小可运行 Agent
需具备：
- Provider 抽象与模型调用：`create_chat_model()`、凭证解析、可替换测试替身
- 消息/会话与 ThreadState：角色、状态容器、序列化、会话隔离
- Prompt 组装与指令层级：system/user/tool 优先级与预算拼装
- 单轮 Agent 图：节点/边、状态转移、终止条件
- 工具调用循环：function calling、工具 schema、观察-行动循环、最大轮次；示例 calculator
- 流式输出/重试/中断：SSE、背压、取消
验收测试：
- tests/chapters/
  - test_ch01_01_config.py
  - test_ch01_02_graph.py
  - test_ch01_02_r0_e2e.py
  - test_ch01_03_messages.py
  - test_ch01_03_prompt.py
  - test_ch01_04_tools.py
  - test_ch01_05_tool_loop.py
  - test_ch01_06_e2e.py

## 第 02 篇 上下文与短期记忆（ch02_*）
文档：agent-book/my-agent-flow-v2/02-上下文与短期记忆
需具备：
- Context Window 预算：token 计量、裁剪策略
- 短期记忆策略：全量 / 滑窗 / 摘要，信息保留对比
- 压缩、自动续写与再注入：长 thread → 压缩 → 仍记得关键事实
- 上下文注入与提示注入防御：不可信数据隔离、扫描与拒绝
验收测试：
- tests/chapters/
  - test_ch02_01_checkpointer.py
  - test_ch02_02_lifecycle.py
  - test_ch02_02_short_term.py
  - test_ch02_03_cli_stdio.py
  - test_ch02_03_compaction.py
  - test_ch02_04_shares.py

## 第 03 篇 工具与行动（ch03_*）
文档：agent-book/my-agent-flow-v2/03-工具与行动
需具备：
- 工具协议与注册，JSON Schema 校验
- 分发器与中间件链：before/after、审计、错误归一
- 宿主边界与直接执行：cwd/env 白名单、路径守卫、超时
- 后台任务与输出快照：启动/查询/取消、环形缓冲
- 浏览器/Computer-Use：一次脚本化点击，鉴权缺失应拒绝
- MCP、插件与 Skills：能力发现与协商（可用假实现）
- 权限、沙箱与审批：最小权限、审批门、危险操作审计
验收测试：
- tests/chapters/
  - test_ch03_01_guard.py
  - test_ch03_02_executor.py
  - test_ch03_02_host_direct.py
  - test_ch03_03_host_tools.py
  - test_ch03_03_middleware.py
  - test_ch03_04_budget.py
  - test_ch03_05_cua.py
  - test_ch03_06_mcp_skills.py
  - test_ch03_07_policy.py

## 第 04 篇 运行状态与持久化（ch04_*）
文档：agent-book/my-agent-flow-v2/04-运行状态与持久化
需具备：
- 消息与会话持久化：关系模型、追加写、会话索引、事务
- Checkpoint 与恢复：状态快照、从下一节点恢复
- 运行生命周期与事件：start/cancel/终态
- 分享、导出与一致性：分享 token、脱敏
验收测试：
- tests/chapters/
  - test_ch04_01_memory.py
  - test_ch04_02_consolidate.py
  - test_ch04_03_assets.py
  - test_ch04_03_chat_flow.py

## 第 05 篇 长期记忆与资产（ch05_*）
文档：agent-book/my-agent-flow-v2/05-长期记忆与资产
需具备：
- 长期记忆写入：atom、namespace、subject_key、revision
- 召回、快照与注入：关键词/向量/混合召回、`<memory>` 注入
- 巩固、冲突与治理：去重、冲突取新值、pin/过期/审计
- 异步抽取与更新队列：LLM 抽取、JSON schema、失败隔离
- 产物、事项与反思：artifact/item/task 契约与稳定 id
验收测试：
- tests/chapters/
  - test_ch05_01_chunker.py
  - test_ch05_02_injection.py
  - test_ch05_02_vector.py
  - test_ch05_03_owned.py
  - test_ch05_04_code_index.py
  - test_ch05_04_updater.py

---
## 交付清单（本阶段完成时应具备）
- 上述测试全部 green（ch01–ch05）
- 最小演示脚本 or `curl` 用例各 1 份/篇（保存到 backend/scripts/ 下）
- `config.yaml` 示例覆盖必要项（模型/存储/工具策略）
- 风险与边界文档：backend/SECURITY-NOTES.md（宿主边界、审批门、配额）

## 备注
- v2 文档为学习顺序与验收口径；参考 v1 与 EvoFlow 仅供对照实现方式与文件地图。
