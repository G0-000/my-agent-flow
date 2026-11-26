"""一、文件说明
    第 4 部分第 3 章：产物契约、用户事项 CRUD 与反射解析。

二、覆盖
    data_dir()                         事项数据和测试缓存隔离到临时目录。
    test_artifact_normalize_and_dedupe() 产物归一化、稳定 id 和批量去重。
    test_artifact_state_key_prefers_path() ThreadState 键优先使用 path。
    test_items_crud_and_filters()      事项创建、查询、更新、删除和过滤。
    test_items_reject_bad_status()     非法事项状态被拒绝。
    test_resolve_variable_and_class()  反射变量/类解析和基类校验。

三、运行
    uv run pytest tests/chapters/test_ch04_03_assets.py -q
"""

from __future__ import annotations

import pytest
from myagentflow.admin.errors import NotFoundError, ValidationError
from myagentflow.artifacts.chat_artifact import (
    artifact_state_key,
    normalize_chat_artifact,
    normalize_chat_artifacts,
)
from myagentflow.config.paths import reset_paths_cache
from myagentflow.items import service, store
from myagentflow.items.models import ItemStatus
from myagentflow.reflection.resolvers import resolve_class, resolve_variable


@pytest.fixture()
def data_dir(tmp_path, monkeypatch):
    """事项 JSON 写临时目录，并清掉进程缓存。"""
    monkeypatch.setenv("MYAF_DATA_DIR", str(tmp_path))
    reset_paths_cache()
    store.reset_store_for_tests()
    yield tmp_path
    store.reset_store_for_tests()
    reset_paths_cache()


def test_artifact_normalize_and_dedupe():
    """图片按扩展名识别；同路径 id 稳定；批量去重。"""
    a = normalize_chat_artifact({"path": "/tmp/a.png", "label": "截图"})
    assert a["type"] == "image" and a["id"] == "path:/tmp/a.png"
    assert normalize_chat_artifact({"path": "/tmp/a.png"})["id"] == a["id"]
    items = normalize_chat_artifacts(
        [{"path": "/tmp/a.png"}, {"path": "/tmp/a.png"}], limit=1
    )
    assert len(items) == 1
    assert normalize_chat_artifact({"content": "", "path": "", "url": ""}) is None


def test_artifact_state_key_prefers_path():
    """ThreadState 字符串键：path > url > id。"""
    assert artifact_state_key({"path": "/a", "url": "http://x"}) == "/a"
    assert artifact_state_key({"url": "http://x"}) == "http://x"


def test_items_crud_and_filters(data_dir):
    """创建 -> 查询 -> 更新 -> 删除；状态标签补齐。"""
    created = service.create_item(title="写周报", tags="工作, 本周", priority="high")
    iid = created["item"]["id"]
    assert created["item"]["status_label"] == "待办"

    listed = service.list_items(q="周报", include_done=False)
    assert listed["total"] == 1
    assert listed["items"][0]["id"] == iid

    updated = service.update_item(iid, {"status": "done", "progress": 100})
    assert updated["item"]["status"] == "done"
    assert updated["item"]["progress"] == 100

    got = service.get_item(iid)
    assert got["item"]["title"] == "写周报"
    assert ItemStatus(updated["item"]["status"]) is ItemStatus.DONE

    assert service.delete_item(iid)["deleted"] == iid
    with pytest.raises(NotFoundError):
        service.get_item(iid)


def test_items_reject_bad_status(data_dir):
    """非法状态不静默降级，直接抛 ValidationError。"""
    with pytest.raises(ValidationError):
        service.create_item(title="x", status="unknown")


def test_resolve_variable_and_class():
    """反射解析：函数对象可直接取；类可按基类校验。"""
    assert resolve_variable("json:dumps") is not None
    assert resolve_class("pathlib:Path") is __import__("pathlib").Path
    with pytest.raises(ImportError):
        resolve_variable("json:not_exists")


def test_items_visibility_scope_filter(data_dir):
    """开启可见性过滤时按 scope 收敛；admin 不过滤；无 scope 看不到任何事项。"""
    a = service.create_item(title="我的", owner_scope_id="personal:u1")
    b = service.create_item(title="别人的", owner_scope_id="personal:u2")
    o = service.create_item(title="组织", owner_scope_id="org:o1")

    res = service.list_items(filter_visibility=True, personal_scope="personal:u1", org_scope="org:o1")
    assert {i["title"] for i in res["items"]} == {"我的", "组织"}
    assert res["total"] == 2

    res = service.list_items(filter_visibility=True)
    assert res["items"] == [] and res["total"] == 0

    res = service.list_items(filter_visibility=True, is_admin=True)
    assert {i["title"] for i in res["items"]} == {"我的", "别人的", "组织"}
    assert {i["id"] for i in res["items"]} == {a["item"]["id"], b["item"]["id"], o["item"]["id"]}
