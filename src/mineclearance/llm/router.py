"""分档路由 + 唯一的记账入口。

为什么必须有这一层：
    12 次是申报表里的承诺。只要有人能绕过预算直接调 client，这个承诺就守不住。
    所以规定：在线调用只能走 Router.call()，它在**发出请求之前**先 budget.check()，
    发完立刻 record()。离线阶段走 Router.offline()，不占在线预算，但单独计数，
    免得以后有人用「反正是离线」当借口把成本藏起来。
"""

from __future__ import annotations

from typing import Dict, Mapping, Optional, Sequence
from urllib.parse import urlsplit
import time
import json
import os
import uuid
from pathlib import Path
from dataclasses import asdict

from ..config import Settings
from ..budget import CallBudget
from .base import LLMClient, LLMError, LLMResponse, Message, TokenCallback

# 阶段 → 档位。这个映射就是「两级裁判切在可判性上」的代码表达：
# 只有 judge_decision 走决策档，其余都要推理。
#
# adversary 自己一档，不与 judge_escalation 共用：升级裁判要复核的正是
# 对抗方参与过的对话，同一个模型既当质询者又当复核者，这次复核等于自己查自己。
# 编排文档表 9 第七行把这条标成「已定」，落点就是这张表。
STAGE_TIER: Dict[str, str] = {
    "adversary": "adversary",
    "judge_decision": "decision",
    "judge_escalation": "reasoning",
    "report": "decision",
}


class Router:
    def __init__(self, clients: Mapping[str, LLMClient], *, vendor_isolated: bool = True, audit_dir: str = "") -> None:
        if not clients:
            raise ValueError("至少需要一档模型")
        self._clients: Dict[str, LLMClient] = dict(clients)
        # 厂商隔离是否真的成立。为假时会话照常跑，但 /v1/health 与 summary() 都如实报告，
        # 不让「只配了一家厂商」伪装成「已按要求交叉」。
        self.vendor_isolated = vendor_isolated
        self.offline_calls = 0
        self.offline_cost_cny = 0.0
        self.audit = []  # 仅服务端持有，含答案的提示词不经学生接口下发。
        self.audit_path = Path(audit_dir) / (uuid.uuid4().hex + ".json") if audit_dir else None

    def _save_audit(self):
        if self.audit_path is not None:
            self.audit_path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.audit_path.with_suffix(".tmp")
            temporary.write_text(json.dumps(self.audit, ensure_ascii=False, indent=2), encoding="utf-8")
            os.replace(temporary, self.audit_path)

    def _complete(self, stage, tier, messages, *, case_evidence_ids=(), **kwargs):
        client = self.client_for(tier)
        entry = {"stage": stage, "tier": tier,
                 "provider": urlsplit(getattr(client, "api_base", "")).hostname or "mock",
                 "model": getattr(client, "model", getattr(client, "name", "unknown")),
                 "messages": [dict(m) for m in messages], "status": "pending"}
        prompt_text = "\n".join(m["content"] for m in messages)
        entry["case_evidence_ids"] = [eid for eid in case_evidence_ids if "[" + eid + "]" in prompt_text]
        self.audit.append(entry)
        started = time.monotonic()
        try:
            response = client.complete(messages, tier=tier, **kwargs)
            entry.update(asdict(response))
            entry["status"] = "ok"
            self._save_audit()
            return response
        except Exception as exc:
            entry.update(status="failed", error=type(exc).__name__,
                         latency_ms=int((time.monotonic() - started) * 1000))
            self._save_audit()
            raise

    def client_for(self, tier: str) -> LLMClient:
        client = self._clients.get(tier)
        if client is None:
            raise LLMError("没有配置 %s 档模型" % tier)
        return client

    def call(
        self,
        stage: str,
        messages: Sequence[Message],
        *,
        budget: CallBudget,
        temperature: float = 0.2,
        on_token: TokenCallback = None,
        case_evidence_ids: Sequence[str] = (),
    ) -> LLMResponse:
        """一次在线调用 = 一次记账。先查额度，再花钱。"""
        tier = STAGE_TIER.get(stage)
        if tier is None:
            raise LLMError(
                "未登记档位的阶段: %s（想新增阶段就必须同时在 STAGE_TIER 与 STAGE_LIMITS 里登记）"
                % stage
            )
        budget.check(stage)
        try:
            response = self._complete(stage, tier, messages, temperature=temperature, on_token=on_token,
                                      case_evidence_ids=case_evidence_ids)
        except Exception:
            budget.record(stage, tier, self.audit[-1]["model"], self.audit[-1]["latency_ms"], 0.0)
            raise
        budget.record(stage, tier, response.model, response.latency_ms, response.cost_cny)
        return response

    def offline(
        self,
        stage: str,
        messages: Sequence[Message],
        *,
        tier: str = "reasoning",
        temperature: float = 0.4,
    ) -> LLMResponse:
        """离线阶段（出题、埋雷）。不占在线预算，单独计数。"""
        if stage == "builder" and "builder" in self._clients:
            tier = "builder"
        self.offline_calls += 1
        response = self._complete(stage, tier, messages, temperature=temperature)
        self.offline_cost_cny = round(self.offline_cost_cny + response.cost_cny, 6)
        return response

    def summary(self) -> Dict[str, object]:
        return {
            "offline_calls": self.offline_calls,
            "offline_cost_cny": self.offline_cost_cny,
            "vendor_isolated": self.vendor_isolated,
            "cost_known": bool(self.audit) and all(a.get("cost_known", False) for a in self.audit),
            "model_routes": {stage: getattr(self.client_for(tier), "model", "mock")
                             for stage, tier in {**STAGE_TIER, "builder": "builder" if "builder" in self._clients else "reasoning", "planter": "reasoning"}.items() if tier in self._clients},
        }


def build_router(settings: Settings) -> Router:
    """按配置拼三档。默认全假模型，保证没有密钥也能跑通。"""
    if settings.use_mock_llm():
        from .mock import MockLLM

        # 演练模式也必须是三个独立实例：隔离机制本身要能被测到，
        # 否则真实模式下它坏了也不会有任何测试先响。
        return Router(
            {
                "decision": MockLLM(name="mock-decision", tier="decision"),
                "reasoning": MockLLM(name="mock-reasoning", tier="reasoning"),
                "adversary": MockLLM(name="mock-adversary", tier="reasoning"),
            },
            vendor_isolated=True,
        )

    from .openai_compat import OpenAICompatLLM

    if not settings.llm_api_base:
        raise LLMError("LLM_PROVIDER 不是 mock 时必须配 LLM_API_BASE")

    clients = {
        "decision": OpenAICompatLLM(
            model=settings.decision_model,
            api_base=settings.llm_api_base,
            api_key=settings.llm_api_key,
            timeout_s=settings.llm_timeout_s,
            max_tokens=settings.llm_max_tokens,
        ),
        "reasoning": OpenAICompatLLM(
            model=settings.reasoning_model,
            api_base=settings.llm_api_base,
            api_key=settings.llm_api_key,
            timeout_s=settings.llm_timeout_s,
            max_tokens=settings.llm_max_tokens,
        ),
    }

    if settings.builder_api_base:
        clients["builder"] = OpenAICompatLLM(
            model=settings.builder_model or settings.reasoning_model,
            api_base=settings.builder_api_base, api_key=settings.builder_api_key,
            auth_header=settings.builder_auth_header, timeout_s=settings.llm_timeout_s,
            max_tokens=settings.llm_max_tokens,
        )

    if settings.adversary_api_base:
        clients["adversary"] = OpenAICompatLLM(
            model=settings.adversary_model or settings.reasoning_model,
            api_base=settings.adversary_api_base,
            api_key=settings.adversary_api_key,
            auth_header=settings.adversary_auth_header,
            timeout_s=settings.llm_timeout_s,
            max_tokens=settings.llm_max_tokens,
        )
        isolated = urlsplit(settings.adversary_api_base).hostname != urlsplit(settings.llm_api_base).hostname
        return Router(clients, vendor_isolated=isolated, audit_dir=settings.llm_audit_dir)

    # 只配了一家厂商：宁可复用也不要中断会话（现场演示不能因为少一个 key 就开不了局），
    # 但隔离不成立这件事必须能被看到，不能由代码替部署方宣称「已交叉」。
    clients["adversary"] = clients["reasoning"]
    return Router(clients, vendor_isolated=False, audit_dir=settings.llm_audit_dir)
