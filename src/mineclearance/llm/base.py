"""模型层的唯一抽象。

上层只认 complete()，不认厂商。换模型只改 .env，不改调用方。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict, Optional, Protocol, Sequence, runtime_checkable

Message = Dict[str, str]
TokenCallback = Optional[Callable[[str], None]]


@dataclass(frozen=True)
class LLMResponse:
    text: str
    model: str
    tier: str
    tokens_in: int
    tokens_out: int
    cost_cny: float
    latency_ms: int


@runtime_checkable
class LLMClient(Protocol):
    def complete(
        self,
        messages: Sequence[Message],
        *,
        tier: str,
        temperature: float = 0.2,
        on_token: TokenCallback = None,
    ) -> LLMResponse:
        ...


class LLMError(RuntimeError):
    pass


def system(text: str) -> Message:
    return {"role": "system", "content": text}


def user(text: str) -> Message:
    return {"role": "user", "content": text}
