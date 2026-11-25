"""一、文件说明
    vector 子包入口：只做模块分组，不重导出，向量存储统一走 sqlite_vec.VectorStore。

二、目录结构
    packages/harness/myagentflow/knowledge/vector/
    ├── __init__.py  ← 本文件
    └── sqlite_vec.py  按 dataset 建表、写入、召回

三、关键方法
    无；公共入口在 sqlite_vec.VectorStore。
"""
