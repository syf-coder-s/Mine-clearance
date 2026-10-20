"""OpenAI 兼容的 chat/completions 客户端。

只用标准库 urllib，不引第三方 SDK：答辩现场网络不好时，少一个依赖少一种崩法。
成本按单价估算，真实账单以网关为准；估不出来就记 0，不要编数字。
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import Any, Dict, Optional, Sequence

from .base import LLMError, LLMResponse, Message, TokenCallback


class OpenAICompatLLM:
    def __init__(
        self,
        model: str,
        api_base: str,
        api_key: str = "",
        *,
        timeout_s: float = 60.0,
        price_in_per_m: float = 0.0,
        price_out_per_m: float = 0.0,
    ) -> None:
        self.model = model
        self.api_base = api_base.rstrip("/")
        self.api_key = api_key
        self.timeout_s = timeout_s
        self.price_in_per_m = price_in_per_m
        self.price_out_per_m = price_out_per_m

    def complete(
        self,
        messages: Sequence[Message],
        *,
        tier: str = "decision",
        temperature: float = 0.2,
        on_token: TokenCallback = None,
    ) -> LLMResponse:
        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": list(messages),
            "temperature": temperature,
            "stream": on_token is not None,
        }
        started = time.time()

        if on_token is not None:
            text, tokens_in, tokens_out = self._stream(payload, on_token)
        else:
            body = self._post(payload)
            choice = (body.get("choices") or [{}])[0]
            text = (choice.get("message") or {}).get("content", "")
            usage = body.get("usage") or {}
            tokens_in = int(usage.get("prompt_tokens", 0))
            tokens_out = int(usage.get("completion_tokens", 0))

        latency_ms = int((time.time() - started) * 1000)
        cost = (
            tokens_in / 1_000_000 * self.price_in_per_m
            + tokens_out / 1_000_000 * self.price_out_per_m
        )
        return LLMResponse(
            text=text,
            model=self.model,
            tier=tier,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            cost_cny=round(cost, 6),
            latency_ms=latency_ms,
        )

    # ---- 传输 ----

    def _headers(self) -> Dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = "Bearer " + self.api_key
        return headers

    def _post(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        request = urllib.request.Request(
            self.api_base + "/chat/completions",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers=self._headers(),
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_s) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:400]
            raise LLMError("模型网关返回 %d: %s" % (exc.code, detail)) from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            raise LLMError("连不上模型网关: %s" % exc) from exc

    def _stream(self, payload: Dict[str, Any], on_token: TokenCallback) -> tuple:
        request = urllib.request.Request(
            self.api_base + "/chat/completions",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers=self._headers(),
            method="POST",
        )
        chunks = []
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_s) as response:
                for raw in response:
                    line = raw.decode("utf-8", "replace").strip()
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        break
                    try:
                        delta = json.loads(data)["choices"][0].get("delta") or {}
                    except (ValueError, KeyError, IndexError):
                        continue
                    piece: Optional[str] = delta.get("content")
                    if piece:
                        chunks.append(piece)
                        if on_token is not None:
                            on_token(piece)
        except (urllib.error.URLError, TimeoutError) as exc:
            raise LLMError("流式传输中断: %s" % exc) from exc
        text = "".join(chunks)
        return text, 0, 0
