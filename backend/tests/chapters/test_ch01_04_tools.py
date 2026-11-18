"""一、文件说明
    第 4 章工具协议：schema 生成、调用与未知工具报错。

二、覆盖
    test_schema_and_call()  echo 生成 function schema，required 正确，调用返回输入。
    test_unknown_tool()     调不存在的工具抛 KeyError。

三、运行
    uv run pytest tests/chapters/test_ch01_04_tools.py -q
"""

from __future__ import annotations

import pytest


def test_schema_and_call():
    """echo 生成 function schema，required 正确，调用返回输入。"""
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
    """调不存在的工具抛 KeyError。"""
    from myagentflow.tools.registry import ToolRegistry

    with pytest.raises(KeyError):
        ToolRegistry().call("nope", {})
