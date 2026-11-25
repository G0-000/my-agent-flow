"""一、文件说明
    embedding 子包入口：只做模块分组，不重导出，调用方统一走 registry。

二、目录结构
    packages/harness/myagentflow/knowledge/embedding/
    ├── __init__.py  ← 本文件
    ├── base.py  接口、错误与缓存
    ├── local_provider.py  离线哈希向量
    └── registry.py  选 provider、批量调用

三、关键方法
    无；公共入口在 registry.get_embedding / get_embeddings。
"""
