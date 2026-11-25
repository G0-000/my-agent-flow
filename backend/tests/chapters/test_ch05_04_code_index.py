"""一、文件说明
    第 5 部分第 4 章：工作区代码索引的符号、全文、增量更新与内部引用。

二、覆盖
    test_index_python_symbols_and_hits()       Python 类/函数可定位到文件与行号。
    test_incremental_update_drops_old_symbol() 改文件后旧符号不残留。
    test_internal_refs_returns_callers()       from import 别名能解析出调用方。
    test_build_index_skips_dependency_dirs()   跳过 .venv，只索引工作区源码。

三、运行
    uv run pytest tests/chapters/test_ch05_04_code_index.py -q
"""

from __future__ import annotations

from myagentflow.code_index.store import build_index, index_file, search_index


def test_index_python_symbols_and_hits(tmp_path):
    """索引后按符号名能拿到准确的 path/line/kind。"""
    root = tmp_path / "repo"
    root.mkdir()
    (root / "service.py").write_text(
        "class Service:\n    def run(self):\n        return 'ok'\n", encoding="utf-8"
    )
    result = index_file(root, relative_path="service.py")
    assert result["action"] == "indexed"
    assert result["symbols"] == 2

    payload = search_index(root, "Service")
    assert payload["hits"][0]["path"] == "service.py"
    assert payload["hits"][0]["line"] == 1
    assert payload["hits"][0]["kind"] == "symbol"


def test_incremental_update_drops_old_symbol(tmp_path):
    """同一文件重索引会先清旧符号，避免 Agent 跳到已删除的函数。"""
    root = tmp_path / "repo"
    root.mkdir()
    path = root / "old.py"
    path.write_text("def old_name():\n    return 1\n", encoding="utf-8")
    index_file(root, relative_path="old.py")

    path.write_text("def new_name():\n    return 2\n", encoding="utf-8")
    index_file(root, relative_path="old.py")
    assert search_index(root, "old_name")["hits"] == []
    assert search_index(root, "new_name")["hits"][0]["line"] == 1


def test_internal_refs_returns_callers(tmp_path):
    """a.py from b import helper 后，搜索 helper 要能返回调用行。"""
    root = tmp_path / "repo"
    root.mkdir()
    (root / "b.py").write_text("def helper():\n    return 1\n", encoding="utf-8")
    (root / "a.py").write_text(
        "from b import helper\n\ndef call():\n    return helper()\n", encoding="utf-8"
    )
    build_index(root)
    payload = search_index(root, "helper")
    assert payload["internal_ref_users"] == [
        {
            "fromPath": "a.py",
            "toPath": "b.py",
            "line": 4,
            "refKind": "call",
            "symbol": "helper",
        }
    ]


def test_build_index_skips_dependency_dirs(tmp_path):
    """build_index 不扫 .venv；文本命中走 FTS。"""
    root = tmp_path / "repo"
    (root / ".venv").mkdir(parents=True)
    (root / ".venv" / "secret.py").write_text(
        "def hidden():\n    pass\n", encoding="utf-8"
    )
    (root / "main.py").write_text(
        "# needle 关键词\ndef visible():\n    pass\n", encoding="utf-8"
    )
    report = build_index(root)
    assert report["indexed"] == 1
    assert search_index(root, "needle")["hits"]
    assert search_index(root, "hidden")["hits"] == []
