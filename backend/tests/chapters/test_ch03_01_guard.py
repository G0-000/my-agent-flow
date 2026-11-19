"""一、文件说明
    03/01 路径守卫：相对路径解析、confine 越界判定、软链逃逸、disabled 放行。

二、覆盖
    test_confine_policy()           confine 下区内文件 resolved，`..` 越界判 escaped。
    test_relative_path_uses_workspace() 相对路径拼到 workspace，不受进程 cwd 影响。
    test_symlink_escape()           软链指向区外时必须判 escaped。
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


def test_relative_path_uses_workspace(tmp_path):
    """相对路径拼到 workspace，不受进程 cwd 影响。"""
    from myagentflow.tools.host_direct.workspace_path_guard import Policy, resolve

    ws = tmp_path / "ws"
    (ws / "sub").mkdir(parents=True)
    result = resolve("sub/a.txt", ws, Policy.confine)
    assert result.inside is True
    assert result.path == (ws / "sub" / "a.txt").resolve()


def test_symlink_escape(tmp_path):
    """软链指向区外时必须判 escaped：只查字符串前缀拦不住。"""
    from myagentflow.tools.host_direct.workspace_path_guard import Policy, resolve

    ws = tmp_path / "ws"
    outside = tmp_path / "outside"
    ws.mkdir()
    outside.mkdir()
    (outside / "secret.txt").write_text("x", encoding="utf-8")
    (ws / "link").symlink_to(outside)

    result = resolve("link/secret.txt", ws, Policy.confine)
    assert result.inside is False
    assert result.decision == "escaped"


def test_disabled_follows_evoflow(tmp_path):
    """disabled 不限制路径，绝对路径照常放行。"""
    from myagentflow.tools.host_direct.workspace_path_guard import Policy, resolve

    assert resolve("/etc/passwd", tmp_path, Policy.disabled).decision == "allowed"
