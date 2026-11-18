"""一、文件说明
    03/01 路径守卫：confine 越界判定与 disabled 放行。

二、覆盖
    test_confine_policy()            confine 下区内文件 resolved，`..` 越界判 escaped。
    test_disabled_follows_evoflow()  disabled 不限制路径，绝对路径照常放行。

三、运行
    uv run pytest tests/chapters/test_ch03_01_guard.py -q
"""

from __future__ import annotations


def test_confine_policy(tmp_path):
    """confine 下区内文件 resolved，`..` 越界判 escaped。"""
    from myagentflow.tools.host_direct.workspace_path_guard import Policy, resolve

    ws = tmp_path / "ws"
    ws.mkdir()
    inside = resolve(str(ws / "a.txt"), ws, Policy.confine)
    assert inside.decision == "resolved" and inside.inside

    outside = resolve(str(ws / ".." / "x.txt"), ws, Policy.confine)
    assert outside.decision == "escaped"


def test_disabled_follows_evoflow(tmp_path):
    """disabled 不限制路径，绝对路径照常放行。"""
    from myagentflow.tools.host_direct.workspace_path_guard import Policy, resolve

    assert resolve("/etc/passwd", tmp_path, Policy.disabled).decision == "allowed"
