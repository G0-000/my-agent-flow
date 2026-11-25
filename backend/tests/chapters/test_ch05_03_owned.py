"""一、文件说明
    第 5 部分第 3 章：Owned Knowledge 的建库、归属过滤、文档切块、目录地图与实体图。

二、覆盖
    test_create_base_filters_owner_scope()   public 对所有 scope 可见，私有库只对本 scope。
    test_upload_markdown_creates_chunks()    上传 Markdown 后文档与块都落库。
    test_folders_include_implicit_parents()   目录地图包含显式与文档路径推导的父目录。
    test_kg_add_triples_and_graph()           三元组写节点/边，graph_payload 可渲染。

三、运行
    uv run pytest tests/chapters/test_ch05_03_owned.py -q
"""

from __future__ import annotations

import pytest
from myagentflow.config.paths import reset_paths_cache
from myagentflow.knowledge.owned import kg, service
from myagentflow.knowledge.owned.db import reset_db_state_for_tests


@pytest.fixture()
def data_dir(tmp_path, monkeypatch):
    """每个用例换独立数据目录，避免 kb 行互相污染。"""
    monkeypatch.setenv("MYAF_DATA_DIR", str(tmp_path))
    reset_paths_cache()
    reset_db_state_for_tests()
    yield tmp_path
    reset_db_state_for_tests()
    reset_paths_cache()


def test_create_base_filters_owner_scope(data_dir):
    """public 库对所有 scope 可见；personal:b 看不到 personal:a 的库。"""
    public = service.create_base({"name": "公共库", "ownerScope": "public"})
    private = service.create_base({"name": "A 的库", "ownerScope": "personal:a"})
    assert {item["kbId"] for item in service.list_bases("personal:a")} == {
        public["kbId"],
        private["kbId"],
    }
    assert {item["kbId"] for item in service.list_bases("personal:b")} == {
        public["kbId"]
    }
    assert service.kb_visible_to_principal(private["kbId"], "personal:a")
    assert not service.kb_visible_to_principal(private["kbId"], "personal:b")


def test_upload_markdown_creates_chunks(data_dir):
    """上传后文档可查，块带 heading_path 且 ordinal 从 0 开始。"""
    kb = service.create_base({"name": "手册"})
    doc = service.upload_manual_markdown(
        kb["kbId"],
        title="部署",
        content="# 部署\n\n使用 uvicorn 启动。\n\n## 回滚\n\n切回上一个版本。",
    )
    assert doc["chunkCount"] >= 1
    assert service.list_documents(kb["kbId"])[0]["id"] == doc["id"]

    chunks = service.list_chunks(doc["id"])
    assert chunks[0]["ordinal"] == 0
    assert chunks[0]["headingPath"]
    assert "部署" in chunks[0]["content"]


def test_folders_include_implicit_parents(data_dir):
    """上传到 work/notes 后，目录地图要自动补出 work 这一层。"""
    kb = service.create_base({"name": "目录测试"})
    service.upload_manual_markdown(
        kb["kbId"], title="笔记", content="# 笔记\n\n正文", folder_path="work/notes"
    )
    folders = service.list_folders(kb["kbId"])
    assert [item["path"] for item in folders] == ["work", "work/notes"]
    assert folders[0]["explicit"] is True

    created = service.create_folder(kb["kbId"], "readme/guides")
    assert created["path"] == "readme/guides"
    assert "readme" in {item["path"] for item in service.list_folders(kb["kbId"])}


def test_kg_add_triples_and_graph(data_dir):
    """两个实体一条边；graph_payload 的 nodes/edges 与 stats 对得上。"""
    kb = service.create_base({"name": "图测试"})
    report = kg.add_triples(kb["kbId"], [("代码索引", "uses", "SQLite FTS5")])
    assert report["edgesAdded"] == 1

    payload = kg.graph_payload(kb["kbId"])
    assert payload["nodeCount"] == 2
    assert payload["edgeCount"] == 1
    assert {node["label"] for node in payload["nodes"]} == {"代码索引", "SQLite FTS5"}
    assert kg.stats(kb["kbId"]) == {"nodeCount": 2, "edgeCount": 1}
    assert kg.find_nodes_by_query(kb["kbId"], "FTS")[0]["name"] == "SQLite FTS5"
