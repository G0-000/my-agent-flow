"""一、文件说明
    第 1 章配置层：环境变量、YAML、providers 布局与模型解析。

二、覆盖
    test_env_model_becomes_primary()      只配环境变量也能建模型，且第一个模型被选为 primary。
    test_blank_base_url_is_none()         空字符串 base_url 归一成 None，避免请求打到空地址。
    test_no_model_raises()                一个模型都没配时抛 NoChatModelConfiguredError，不静默开跑。
    test_yaml_config_defines_models()     YAML 里的 log_level、primary_model 与模型条目都被读进来。
    test_config_path_env_override()       改 MYAF_CONFIG_PATH 后解析结果跟着变，说明没有走旧缓存。
    test_providers_layout_is_flattened()  providers 嵌套写法被摊平成扁平模型列表，顺序保持。

    test_stub_vendor()                   vendor=stub 时工厂返回 StubChatModel，invoke 回显。
    test_stub_vendor_bad_use()           use 字段写错时明确报错，不静默回退。
    test_unknown_vendor_raises()         未实现的 vendor 直接报错。
三、运行
    uv run pytest tests/chapters/test_ch01_01_config.py -q
"""

from __future__ import annotations

import pytest


def _isolate(monkeypatch, tmp_path):
    """把 cwd 挪到 tmp，避免读到仓库里真实的 config.yaml；清掉相关 env。"""
    for k in (
        "MYAGENTFLOW_CONFIG_PATH",
        "MYAF_MODEL_NAME",
        "MYAF_MODEL_ID",
        "MYAF_MODEL_VENDOR",
        "MYAF_MODEL_BASE_URL",
        "MYAF_MODEL_API_KEY",
    ):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.chdir(tmp_path)


def test_env_model_becomes_primary(monkeypatch, tmp_path):
    """只配环境变量也能建模型，且第一个模型被选为 primary。"""
    from myagentflow.config.app_config import get_app_config, reset_app_config

    _isolate(monkeypatch, tmp_path)
    reset_app_config()
    monkeypatch.setenv("MYAF_MODEL_NAME", "local")
    monkeypatch.setenv("MYAF_MODEL_ID", "gpt-4o-mini")

    cfg = get_app_config()
    assert cfg.primary_model == "local"
    assert cfg.models[0].vendor == "openai"
    assert cfg.models[0].model == "gpt-4o-mini"  # model 是模型 ID，name 是条目名
    assert cfg.checkpointer.type == "memory"
    assert cfg.storage.backend == "sqlite"


def test_blank_base_url_is_none(monkeypatch, tmp_path):
    """空字符串 base_url 归一成 None，避免请求打到空地址。"""
    from myagentflow.config.app_config import get_app_config, reset_app_config

    _isolate(monkeypatch, tmp_path)
    reset_app_config()
    monkeypatch.setenv("MYAF_MODEL_NAME", "m")
    monkeypatch.setenv("MYAF_MODEL_BASE_URL", "")  # 空字符串当「没配」

    assert get_app_config().models[0].base_url is None


def test_no_model_raises(monkeypatch, tmp_path):
    """一个模型都没配时抛 NoChatModelConfiguredError，不静默开跑。"""
    from myagentflow.config.app_config import get_app_config, reset_app_config
    from myagentflow.models.resolver import (
        NoChatModelConfiguredError,
        resolve_run_model,
    )

    _isolate(monkeypatch, tmp_path)
    reset_app_config()

    with pytest.raises(NoChatModelConfiguredError):
        resolve_run_model()
    assert get_app_config().models == []


def test_yaml_config_defines_models(monkeypatch, tmp_path):
    """YAML 里的 log_level、primary_model 与模型条目都被读进来。"""
    from myagentflow.config.app_config import get_app_config, reset_app_config

    _isolate(monkeypatch, tmp_path)
    (tmp_path / "config.yaml").write_text(
        """
log_level: debug
primary_model: local
models:
  - name: local
    vendor: openai
    use: langchain_openai:ChatOpenAI
    model: gpt-4o-mini
    base_url: http://127.0.0.1:1234/v1
    api_key: sk-test
checkpointer:
  type: sqlite
  connection_string: data/checkpoints.db
""".lstrip(),
        encoding="utf-8",
    )
    reset_app_config()

    cfg = get_app_config()
    assert cfg.log_level == "debug"
    assert cfg.primary_model == "local"
    assert cfg.models[0].name == "local"
    assert cfg.models[0].model == "gpt-4o-mini"
    assert cfg.models[0].base_url == "http://127.0.0.1:1234/v1"
    assert cfg.checkpointer.type == "sqlite"
    assert cfg.checkpointer.connection_string == "data/checkpoints.db"


def test_config_path_env_override(monkeypatch, tmp_path):
    """改 MYAF_CONFIG_PATH 后解析结果跟着变，说明没有走旧缓存。"""
    from myagentflow.config.app_config import get_app_config, reset_app_config
    from myagentflow.models.resolver import resolve_run_model

    _isolate(monkeypatch, tmp_path)
    alt = tmp_path / "alt.yaml"
    alt.write_text(
        "primary_model: alt\nmodels:\n  - name: alt\n    model: m1\n    use: langchain_openai:ChatOpenAI\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("MYAGENTFLOW_CONFIG_PATH", str(alt))
    reset_app_config()

    assert resolve_run_model() == "alt"
    assert get_app_config().models[0].model == "m1"


def test_providers_layout_is_flattened(monkeypatch, tmp_path):
    """yaml 也可以按网关分组写 providers，进 AppConfig 前要摊平成一条一模型。"""
    from myagentflow.config.app_config import get_app_config, reset_app_config

    _isolate(monkeypatch, tmp_path)
    (tmp_path / "config.yaml").write_text(
        """
primary_model: fast
models:
  providers:
    local-gateway:
      vendor: openai
      use: langchain_openai:ChatOpenAI
      base_url: http://127.0.0.1:1234/v1
      api_key: sk-local
      models:
        - name: fast
          model: gpt-4o-mini
        - name: slow
          model: gpt-4o
""".lstrip(),
        encoding="utf-8",
    )
    reset_app_config()

    cfg = get_app_config()
    assert [m.name for m in cfg.models] == ["fast", "slow"]
    assert cfg.models[0].vendor == "openai"
    assert cfg.models[0].base_url == "http://127.0.0.1:1234/v1"  # provider 层共享值下传
    assert cfg.models[0].model == "gpt-4o-mini"



def test_stub_vendor(monkeypatch, tmp_path):
    """vendor=stub 时工厂返回 StubChatModel，invoke 回显最后一条用户消息（echo: 前缀）。"""
    from langchain_core.messages import HumanMessage
    from myagentflow.config.app_config import reset_app_config
    from myagentflow.models.factory import create_chat_model
    from myagentflow.models.providers.stub import StubChatModel

    _isolate(monkeypatch, tmp_path)
    (tmp_path / "config.yaml").write_text(
        """
primary_model: local
models:
  - name: local
    vendor: stub
    use: myagentflow.models.providers.stub:StubChatModel
    model: stub
    temperature: 0.0
""".lstrip(),
        encoding="utf-8",
    )
    reset_app_config()

    model = create_chat_model()
    assert isinstance(model, StubChatModel)
    reply = model.invoke([HumanMessage(content="你好")])
    assert str(reply.content) == "echo: 你好"


def test_stub_vendor_bad_use(monkeypatch, tmp_path):
    """use 字段不是 'package:Class' 形式时，工厂明确报错而不是静默回退。"""
    from myagentflow.config.app_config import reset_app_config
    from myagentflow.models.factory import create_chat_model

    _isolate(monkeypatch, tmp_path)
    (tmp_path / "config.yaml").write_text(
        """
primary_model: local
models:
  - name: local
    vendor: stub
    use: not-a-valid-use-path
    model: stub
""".lstrip(),
        encoding="utf-8",
    )
    reset_app_config()

    with pytest.raises(RuntimeError):
        create_chat_model()


def test_unknown_vendor_raises(monkeypatch, tmp_path):
    """未实现的 vendor 直接报错，错误信息列出已实现项（openai、stub）。"""
    from myagentflow.config.app_config import reset_app_config
    from myagentflow.models.factory import create_chat_model

    _isolate(monkeypatch, tmp_path)
    (tmp_path / "config.yaml").write_text(
        """
primary_model: local
models:
  - name: local
    vendor: anthropic
    use: somewhere:Something
    model: claude
""".lstrip(),
        encoding="utf-8",
    )
    reset_app_config()

    with pytest.raises(RuntimeError, match="vendor"):
        create_chat_model()
