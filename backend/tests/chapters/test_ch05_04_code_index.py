from __future__ import annotations


def test_index(tmp_path):
    from myagentflow.code_index.store import CodeIndex

    src = tmp_path / "demo.py"
    src.write_text("class A:\n    def m(self):\n        pass\n\ndef f():\n    pass\n", encoding="utf-8")

    idx = CodeIndex(tmp_path / "c.sqlite")
    idx.add_file(src)
    assert idx.find("A")[0]["line"] == 1
    assert idx.find("m")[0]["kind"] == "function"
    assert idx.find("f")[0]["line"] == 5
