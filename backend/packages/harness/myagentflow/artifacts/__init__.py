"""一、文件说明
    artifacts 包入口：只做模块分组，不重导出；调用方直接走 chat_artifact。

二、目录结构
    packages/harness/myagentflow/artifacts/
    ├── __init__.py      ← 本文件
    └── chat_artifact.py  产物规范化与落盘

三、关键方法
    无；公共入口在 artifacts.chat_artifact。
"""
