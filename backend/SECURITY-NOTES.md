# SECURITY NOTES (local dev)

本仓库包含一套用于章节学习的最小实现。请注意：

- stub provider（myagentflow.models.providers.stub.StubChatModel）仅用于本地开发/测试；
  - 不联网、可预测输出；
  - 切勿在生产环境或公开部署时启用。
- tools/ 目录涉及对宿主的访问（如 shell、workspace_files）：
  - 默认仅用于受控环境；
  - 任何危险操作应设置审批门与路径白名单；
  - 超时、预算与输出截断策略需要在后续章节中继续完善。

以上约束请在演示和测试时遵守。
