from __future__ import annotations

import pytest


def test_schema_and_call():
    from myagentflow.tools.builtins.echo import register_echo
    from myagentflow.tools.registry import ToolRegistry

    r = ToolRegistry()
    register_echo(r)
    schema = r.schemas()[0]
    assert schema["type"] == "function"
    assert schema["function"]["name"] == "echo"
    assert schema["function"]["parameters"]["required"] == ["text"]
    assert r.call("echo", {"text": "hi"}) == "hi"


def test_unknown_tool():
    from myagentflow.tools.registry import ToolRegistry

    with pytest.raises(KeyError):
        ToolRegistry().call("nope", {})
