from __future__ import annotations


def test_defaults(monkeypatch):
    for k in ("MYAF_MODEL_PROVIDER", "MYAF_MODEL_NAME", "MYAF_MODEL_BASE_URL",
              "MYAF_MODEL_API_KEY", "MYAF_DATA_DIR", "MYAF_CHECKPOINTER"):
        monkeypatch.delenv(k, raising=False)

    from myagentflow.config.settings import load_config

    cfg = load_config()
    assert cfg.model.provider == "openai"
    assert cfg.model.name == "gpt-4o-mini"
    assert cfg.checkpointer == "memory"


def test_blank_base_url_is_none(monkeypatch):
    monkeypatch.setenv("MYAF_MODEL_BASE_URL", "")
    from myagentflow.config.settings import load_config

    assert load_config().model.base_url is None
