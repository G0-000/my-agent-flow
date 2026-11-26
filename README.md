# my-agent-flow

基于 EvoFlow `f22af53910a470ddba633be35e25878214c2984ec`（v1.3.22）的学习与独立仿写项目。

## 文档位置

开始修改文档或代码前，请先读 [`AI协作编写规则.md`](../agent-book/my-agent-flow/AI协作编写规则.md)。

- **站点分章正文（唯一维护来源）**：`/Users/main/agent-book/my-agent-flow/`（Part 00–13）
- **分章与本地代码对照**：`/Users/main/agent-book/my-agent-flow/00-导论/06-总文档分章与代码落地对照.md`
- **单文件合订本**：`../agent-book/my-agent-flow/EvoFlow-学习规划-总文档.md`，由 Agent-Book 脚本生成，禁止直接手改。
- **溯源归档**：`/Users/main/agent-book/my-agent-flow/溯源/`

> 分章目录现有 58 篇教材章节正文（00 导论 6 篇、Part 01–13 共 52 篇），另有各 Part README 与逐章代码落地审计附页。合订本按脚本收录口径当前为 73 篇、570,318 字符 / 16,230 行，已重建核验。

合订本构建方式：

```bash
cd /Users/main/agent-book && python3 scripts/build_evoflow_master.py
```

## 章节与代码

- 章节安排与逐章状态见 Agent-Book 的 `README.md`、`PROGRESS.md` 及“总文档分章与代码落地对照”。
- 代码在 `backend/`，核心包是 `backend/packages/harness/myagentflow/`，应用入口在 `backend/app/`，章节测试在 `backend/tests/chapters/`。
- 组件实现、章节测试、接入真实请求路径是三个不同状态；不要将组件通过描述成产品全链路完成。
- Python ≥ 3.12，使用 `uv`；数据库 SQLite；密钥与运行数据不入库。
- EvoFlow 使用 PolyForm Noncommercial 1.0.0；本项目是独立学习实现，不整段复制上游源码。

## 开始

```bash
cd backend
uv sync
cp config.example.yaml config.yaml
```
