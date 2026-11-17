"""第 1 章 / 配置层测试：对齐 EvoFlow `config/app_config.py` 的字段与函数名。"""
from __future__ import annotations

import pytest


def _isolate(monkeypatch, tmp_path):
    """把 cwd 挪到 tmp，避免读到仓库里真实的 config.yaml；清掉相关 env。"""
    for k in (
        "MYAGENTFLOW_CONFIG_PATH",
        "MYAF_MODEL_NAME",
        "MYAF_MODEL_VENDOR",
        "MYAF_MODEL_BASE_URL",
        "MYAF_MODEL_API_KEY",
        "MYAF_CHECKPOINTER",
        "MYAF_CHECKPOINT_SQLITE_PATH",
    ):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.chdir(tmp_path)


def test_env_model_becomes_primary(monkeypatch, tmp_path):
    from myagentflow.config.app_config import get_app_config, reset_app_config

    _isolate(monkeypatch, tmp_path)
    reset_app_config()
    monkeypatch.setenv("MYAF_MODEL_NAME", "gpt-4o-mini")

    cfg = get_app_config()
    assert cfg.primary_model == "gpt-4o-mini"
    assert cfg.get_model().vendor == "openai"
    assert cfg.checkpointer.type == "memory"
    assert cfg.storage.backend == "sqlite"


def test_blank_base_url_is_none(monkeypatch, tmp_path):
    from myagentflow.config.app_config import get_app_config, reset_app_config

    _isolate(monkeypatch, tmp_path)
    reset_app_config()
    monkeypatch.setenv("MYAF_MODEL_NAME", "m")
    monkeypatch.setenv("MYAF_MODEL_BASE_URL", "")  # 空字符串当「没配」

    assert get_app_config().get_model().base_url is None


def test_no_model_raises(monkeypatch, tmp_path):
    from myagentflow.config.app_config import (
        NoChatModelConfiguredError,
        get_app_config,
        reset_app_config,
    )

    _isolate(monkeypatch, tmp_path)
    reset_app_config()

    with pytest.raises(NoChatModelConfiguredError):
        get_app_config().get_model()


def test_yaml_config_defines_models(monkeypatch, tmp_path):
    from myagentflow.config.app_config import get_app_config, reset_app_config

    _isolate(monkeypatch, tmp_path)
    (tmp_path / "config.yaml").write_text(
        """
log_level: debug
primary_model: local
models:
  - name: local
    vendor: openai
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
    assert cfg.get_model().base_url == "http://127.0.0.1:1234/v1"
    assert cfg.checkpointer.type == "sqlite"
    assert cfg.checkpointer.connection_string == "data/checkpoints.db"


def test_config_path_env_override(monkeypatch, tmp_path):
    from myagentflow.config.app_config import get_app_config, reset_app_config

    _isolate(monkeypatch, tmp_path)
    alt = tmp_path / "alt.yaml"
    alt.write_text("primary_model: alt\nmodels:\n  - name: alt\n", encoding="utf-8")
    monkeypatch.setenv("MYAGENTFLOW_CONFIG_PATH", str(alt))
    reset_app_config()

    assert get_app_config().get_model().name == "alt"
