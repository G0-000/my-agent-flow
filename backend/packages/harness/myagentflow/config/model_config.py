"""单个模型的配置：连接信息 + 采样参数。

两个最容易混的字段：
    name  —— 配置条目名（唯一），primary_model 引用它，也用来在列表里回查
    model —— 真正发给厂商的模型 ID（如 gpt-4o-mini）

本文件只保留第 1 章用得到的 13 列；其余列名列在文末注释里，读到对应章节再加。
"""


from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

# 单轮输出预算默认值：多数 OpenAI 兼容网关按这个上限截断一次输出
DEFAULT_MODEL_MAX_OUTPUT_TOKENS = 65536
# 历史默认值：早期面板统一写 8192。现在读到这个值要当成「没配」升级到 65536，
# 否则老配置文件会把输出硬卡在 8K。
_LEGACY_DEFAULT_MAX_OUTPUT_TOKENS = 8192


def resolve_model_max_output_tokens(raw: int | None) -> int:
    """把 DB/API 里的 max_tokens 归一：未设或历史 8192 → 64k。

    含 8192 这个历史值特判：老配置把它当默认写死，读到就该升级，而不是照用。
    """
    if raw is None or raw <= 0:
        return DEFAULT_MODEL_MAX_OUTPUT_TOKENS
    if raw == _LEGACY_DEFAULT_MAX_OUTPUT_TOKENS:
        return DEFAULT_MODEL_MAX_OUTPUT_TOKENS
    return int(raw)


class ModelConfig(BaseModel):
    """一条模型的配置。"""

    @model_validator(mode="before")
    @classmethod
    def _drop_reserved_model_config_key(cls, data: Any) -> Any:
        """Pydantic 的类级配置叫 model_config，数据里混进来同名键要剔掉。

        不剔掉就会和 Pydantic 的类级配置撞名，建类直接失败。
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

    # 余下未加的列（读到相应章节再补，命名保持同一套）：
    # supports_thinking / supports_reasoning_effort / when_thinking_enabled /
    # supports_vision / enable_web_search / web_search_options / credentials /
    # credential_strategy / fallback_models / availability_status /
    # unavailable_reason / unavailable_code / unavailable_at / thinking /
    # input_context_length / output_context_length / use_responses_api / output_version
