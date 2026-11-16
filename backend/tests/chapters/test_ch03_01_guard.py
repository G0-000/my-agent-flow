from __future__ import annotations


def test_confine_policy(tmp_path):
    from myagentflow.tools.host_direct.workspace_path_guard import Policy, resolve

    ws = tmp_path / "ws"
    ws.mkdir()
    inside = resolve(str(ws / "a.txt"), ws, Policy.confine)
    assert inside.decision == "resolved" and inside.inside

    outside = resolve(str(ws / ".." / "x.txt"), ws, Policy.confine)
    assert outside.decision == "escaped"


def test_disabled_follows_evoflow(tmp_path):
    from myagentflow.tools.host_direct.workspace_path_guard import Policy, resolve

    assert resolve("/etc/passwd", tmp_path, Policy.disabled).decision == "allowed"
