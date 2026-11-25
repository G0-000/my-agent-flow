"""一、文件说明
    items 包入口：只做模块分组，不重导出；调用方直接走 service。

二、目录结构
    packages/harness/myagentflow/items/
    ├── __init__.py  ← 本文件
    ├── models.py   事项模型与状态/优先级白名单
    ├── store.py    JSON 持久化
    └── service.py  CRUD、过滤、分页

三、关键方法
    无；公共入口在 items.service。
"""
