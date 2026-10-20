"""模型层。

对外只暴露 Router：所有在线调用都必须经过它，因为它是唯一记账的地方。
直接拿 client 去调，等于绕过预算，评审演示时会当场翻车。
"""

from .base import LLMClient, LLMError, LLMResponse, Message, TokenCallback, system, user
from .mock import EchoLLM, MockLLM
from .openai_compat import OpenAICompatLLM
from .router import STAGE_TIER, Router, build_router

__all__ = [
    "Message",
    "TokenCallback",
    "LLMResponse",
    "LLMClient",
    "LLMError",
    "system",
    "user",
    "MockLLM",
    "EchoLLM",
    "OpenAICompatLLM",
    "Router",
    "STAGE_TIER",
    "build_router",
]
