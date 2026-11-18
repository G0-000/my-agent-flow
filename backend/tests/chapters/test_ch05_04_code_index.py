"""一、文件说明
    05/04 代码索引：模块/类/函数的行号与类型。

二、覆盖
    test_index()  索引能定位类、方法与函数的行号与类型。

三、运行
    uv run pytest tests/chapters/test_ch05_04_code_index.py -q
"""

from __future__ import annotations


def test_index(tmp_path):
    """索引能定位类、方法与函数的行号与类型。"""
    from myagentflow.code_index.store import CodeIndex

    src = tmp_path / "demo.py"
    src.write_text("class A:\n    def m(self):\n        pass\n\ndef f():\n    pass\n", encoding="utf-8")

    idx = CodeIndex(tmp_path / "c.sqlite")
    idx.add_file(src)
    assert idx.find("A")[0]["line"] == 1
    assert idx.find("m")[0]["kind"] == "function"
    assert idx.find("f")[0]["line"] == 5
