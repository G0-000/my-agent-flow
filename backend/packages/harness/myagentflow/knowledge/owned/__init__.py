"""一、文件说明
    owned 子包入口：只做模块分组，不重导出，避免调用方绕过 service/kg。

二、目录结构
    packages/harness/myagentflow/knowledge/owned/
    ├── __init__.py  ← 本文件
    ├── db.py  连接与锁
    ├── ids.py  id 与时间
    ├── schema.py  表结构
    ├── service.py  知识库、文档、目录与块
    └── kg.py  实体图节点与边

三、关键方法
    无；公共入口在 service / kg。
"""
