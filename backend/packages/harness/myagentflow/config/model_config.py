"""单个模型的配置节。

对照 EvoFlow `config/model_config.py`：文件名、类名、字段名一致，
只保留第 1 章用得到的字段（EvoFlow 原文件 183 行、30 列，其余列见文件末尾注释）。

注意 EvoFlow 的两个名字不是一回事：
    name  —— 这条配置的**条目名**（唯一键，primary_model 里引用的就是它）
    model —— 真正发请求时用的**模型 ID**（如 gpt-4o-mini）
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

# 单轮输出预算默认值（EvoFlow 同名常量，`model_config.py:6`）
DEFAULT_MODEL_MAX_OUTPUT_TOKENS = 65536
# 历史默认值：早期面板统一写 8192。现在读到这个值要当成「没配」升级到 65536，
# 否则老配置文件会把输出硬卡在 8K。
_LEGACY_DEFAULT_MAX_OUTPUT_TOKENS = 8192


def resolve_model_max_output_tokens(raw: int | None) -> int:
    """把 DB/API 里的 max_tokens 归一：未设或历史 8192 → 64k。

    直接照抄 EvoFlow `model_config.py:10` 的语义（含 8192 这个历史值特判）。
    """
    if raw is None or raw <= 0:
        return DEFAULT_MODEL_MAX_OUTPUT_TOKENS
    if raw == _LEGACY_DEFAULT_MAX_OUTPUT_TOKENS:
        return DEFAULT_MODEL_MAX_OUTPUT_TOKENS
    return int(raw)


class ModelConfig(BaseModel):
    """Config section for a model（与 EvoFlow `model_config.py:78` 同名同义）。"""

    @model_validator(mode="before")
    @classmethod
    def _drop_reserved_model_config_key(cls, data: Any) -> Any:
        """Pydantic 的类级配置叫 model_config，数据里混进来同名键要剔掉。

        EvoFlow 也写了这个校验器，原因相同，照抄。
        """
        if isinstance(data, dict) and "model_config" in data:
            data = dict(data)
            data.pop("model_config", None)
        return data

    vendor: str | None = Field(default=None, description="英文厂商 id（openai/aliyun/...）")
    name: str = Field(..., description="这条配置的唯一名称，primary_model 引用它")
    display_name: str | None = Field(default=None, description="界面上显示的名字")
    description: str | None = Field(default=None, description="说明")
    use: str = Field(..., description="provider 类路径，如 langchain_openai:ChatOpenAI")
    model: str = Field(..., description="真实模型 ID")

    # 连接
    base_url: str | None = Field(default=None, description="自建网关地址")
    api_key: str | None = Field(default=None, description="密钥")

    # 参数
    request_timeout: float | None = Field(default=None, description="请求超时（秒）")
    max_retries: int | None = Field(default=None, description="重试次数")
    max_tokens: int | None = Field(default=None, description="单轮输出上限，未设按 65536")
    context_length: int | None = Field(default=None, description="输入上下文窗口")
    temperature: float | None = Field(default=None, description="采样温度")

    model_config = ConfigDict(extra="allow")

    # 余下未抄的列（读到相应章节再补，列名照 EvoFlow）：
    # supports_thinking / supports_reasoning_effort / when_thinking_enabled /
    # supports_vision / enable_web_search / web_search_options / credentials /
    # credential_strategy / fallback_models / availability_status /
    # unavailable_reason / unavailable_code / unavailable_at / thinking /
    # input_context_length / output_context_length / use_responses_api / output_version
