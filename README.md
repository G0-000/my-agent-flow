# my-agent-flow

基于 EvoFlow 最新源码（`f22af53910a470ddba633be35e25878214c2984ec`，v1.3.22）的 0→1 复刻项目。

## 文档在哪里

开始编写或修改本项目文档、仿写代码前，先阅读 [`AI协作编写规则.md`](AI协作编写规则.md)。它约束章节推进、EvoFlow 源码对照、代码范围以及总文档与拆分正文的同步方式。

正文在 Agent-Book，本仓库额外保留一份**合订本**，方便整份投喂给其他 AI。

- **合订本（单文件，推荐给外部 AI）**：`EvoFlow-学习规划-总文档.md`（71 篇合并，约 450 KB）
- 正文（13 个 Part）：`agent-book` 仓库的 `work-agent-harness/doc/evoflow-学习规划/`
- 渲染入口（独立分区）：`agent-book` 仓库的 `my-agent-flow/index.md` → 站点 `/agent-book/my-agent-flow/`
- 溯源归档：同目录 `溯源/`（`EvoFlow从0到1复刻手册.md`、单文件版学习规划）

合订本由 `agent-book/scripts/build_evoflow_master.py` 自动生成，**不要手改**：

```bash
cd ../agent-book && python3 scripts/build_evoflow_master.py
```

原「主文档」即 `溯源/EvoFlow从0到1复刻手册.md`，每章固定六段：

1. 功能理解（用户能做什么）
2. 源码导读（教材读哪几个文件、按什么顺序读）
3. 顺序执行链（请求 → 步骤 → 注释）
4. 自己要写什么（目标文件与接口）
5. 一步步实现（L1 最小闭环 → L2 真实入口 → L3 功能补齐 → L4 失败边界，含代码骨架）
6. 验收（命令、预期、依赖真假）

章节安排：第 0 章全局认识（功能地图、架构、目录、验收口径）→ 第 1–4 章跑通配置/模型/单轮/持久化 → 第 5–7 章工具/中间件/事件流 → 第 8–9 章上下文与记忆 → 第 10–13 章知识/子代理/计划/外部生态 → 第 14–16 章 Gateway/治理/产品面收口。附录含功能状态总表、数据表汇总、验收模板、常见坑、分章源码阅读清单。

## 目录

```
my-agent-flow/
├── backend/
│   ├── pyproject.toml             # uv workspace
│   ├── langgraph.json             # 图与 checkpointer 注册
│   ├── config.example.yaml        # 配置样例
│   ├── packages/harness/myagentflow/  # 核心层（禁止 import app.*）
│   ├── app/                       # 应用层：gateway / channels
│   └── tests/chapters/            # 按章验收测试
└── .gitignore                     # .env / config.yaml / data/ 已忽略
```

## 约定

- Python ≥ 3.12，包管理用 `uv`；数据库 SQLite；包名 `myagentflow`。
- 先用 fake 模型 + 内存/SQLite 跑通最小闭环，再接真实模型。
- 密钥与运行数据不入库；文档只写占位符。
- EvoFlow 为 PolyForm Noncommercial 许可：只学习架构与行为，不整段复制源码。

## 开始

```bash
cd backend
uv sync
cp config.example.yaml config.yaml
```

然后按 `agent-book/work-agent-harness/doc/evoflow-学习规划/01-最小闭环/01-配置与模型` 的顺序，从 `myagentflow/config`、`myagentflow/models` 开始写。
