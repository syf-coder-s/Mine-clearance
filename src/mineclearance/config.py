"""全局配置。一个冻结对象，从环境变量读，读一次。

原则：预算相关的数字只在这里出现一次，别处引用 config，不写字面量。
"""

from __future__ import annotations

import os
from dataclasses import dataclass


def _get_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _get_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    return default if raw is None or raw.strip() == "" else float(raw)


def _get_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    return default if raw is None or raw.strip() == "" else int(raw)


@dataclass(frozen=True)
class Settings:
    llm_provider: str = "mock"
    llm_api_base: str = ""
    llm_api_key: str = ""
    decision_model: str = "mock-decision"
    reasoning_model: str = "mock-reasoning"
    builder_api_base: str = ""
    builder_api_key: str = ""
    builder_model: str = ""
    builder_auth_header: str = "Authorization"
    adversary_auth_header: str = "Authorization"
    llm_timeout_s: float = 120.0
    llm_max_tokens: int = 4096
    llm_audit_dir: str = ""

    # 对抗方单独一家，理由见编排文档表 9 第七行：禁止同一模型既当对抗又当裁判。
    # 升级裁判要复核的就是对抗方参与过的对话，同源时这次复核等于自己查自己。
    # 留空时回退到 reasoning 档，会话照常跑，但 Router.vendor_isolated 会是 False，
    # /v1/health 上看得到——降级可以，假装做到了不行。
    adversary_api_base: str = ""
    adversary_api_key: str = ""
    adversary_model: str = ""

    rag_base_url: str = ""
    rag_api_key: str = ""
    rag_timeout_s: float = 2.0
    rag_top_k: int = 10
    rag_judge_top_k: int = 3
    # 判例库独立于本题原始代码，不能把判例里的代码当作本题事实。
    rag_provider: str = "contract"
    ragflow_base_url: str = ""
    ragflow_api_key: str = ""
    ragflow_dataset_id: str = ""
    ragflow_pattern_dataset_id: str = ""
    ragflow_negative_dataset_id: str = ""
    ragflow_timeout_s: float = 15.0
    ragflow_cache_ttl_s: float = 300.0
    case_top_k: int = 3
    case_candidate_k: int = 10
    case_min_similarity: float = 0.1
    pattern_candidate_k: int = 4
    pattern_min_similarity: float = 0.25
    negative_candidate_k: int = 4
    negative_min_similarity: float = 0.25
    case_snapshot_dir: str = "data/case_snapshots"

    # 裁决层（状态机 / 两段式预算 / 锚点）。留空 = 内存实现 FakeUpstream，
    # 七个端点照常可用；填上就整体切到 HttpUpstream，不做半截降级。
    upstream_base_url: str = ""
    upstream_api_key: str = ""
    upstream_timeout_s: float = 3.0

    # 内部令牌：锚点永不下发学生，/v1/anchor/* 只对带这个头的调用方开放。
    # 留空 = 一律 403，宁可不给，也不默认敞开。
    internal_token: str = ""

    max_calls_per_session: int = 12
    cost_budget_cny: float = 0.08
    min_rounds: int = 2
    max_rounds: int = 3
    # 与编排文档表 9 第二行一致：先按 0.8 起，用自建 200 条样本标定后冻结。
    # 这个数字只在这里出现一次，judge.py 的提示词按它动态注入，不各写一份。
    escalate_confidence: float = 0.8
    prefetch: bool = True
    items_per_session: int = 3

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            llm_provider=os.getenv("LLM_PROVIDER", "mock"),
            llm_api_base=os.getenv("LLM_API_BASE", ""),
            llm_api_key=os.getenv("LLM_API_KEY", ""),
            decision_model=os.getenv("DECISION_MODEL", "mock-decision"),
            reasoning_model=os.getenv("REASONING_MODEL", "mock-reasoning"),
            builder_api_base=os.getenv("BUILDER_API_BASE", ""),
            builder_api_key=os.getenv("BUILDER_API_KEY", ""),
            builder_model=os.getenv("BUILDER_MODEL", ""),
            builder_auth_header=os.getenv("BUILDER_AUTH_HEADER", "Authorization"),
            adversary_auth_header=os.getenv("ADVERSARY_AUTH_HEADER", "Authorization"),
            llm_timeout_s=_get_float("LLM_TIMEOUT_S", 120.0),
            llm_max_tokens=_get_int("LLM_MAX_TOKENS", 4096),
            llm_audit_dir=os.getenv("LLM_AUDIT_DIR", ""),
            adversary_api_base=os.getenv("ADVERSARY_API_BASE", ""),
            adversary_api_key=os.getenv("ADVERSARY_API_KEY", ""),
            adversary_model=os.getenv("ADVERSARY_MODEL", ""),
            rag_base_url=os.getenv("RAG_BASE_URL", ""),
            rag_api_key=os.getenv("RAG_API_KEY", ""),
            rag_timeout_s=_get_float("RAG_TIMEOUT_S", 2.0),
            rag_top_k=_get_int("RAG_TOP_K", 10),
            rag_judge_top_k=_get_int("RAG_JUDGE_TOP_K", 3),
            rag_provider=os.getenv("RAG_PROVIDER", "contract"),
            ragflow_base_url=os.getenv("RAGFLOW_BASE_URL", ""),
            ragflow_api_key=os.getenv("RAGFLOW_API_KEY", ""),
            ragflow_dataset_id=os.getenv("RAGFLOW_DATASET_ID", ""),
            ragflow_pattern_dataset_id=os.getenv("RAGFLOW_PATTERN_DATASET_ID", ""),
            ragflow_negative_dataset_id=os.getenv("RAGFLOW_NEGATIVE_DATASET_ID", ""),
            ragflow_timeout_s=_get_float("RAGFLOW_TIMEOUT_S", 15.0),
            ragflow_cache_ttl_s=_get_float("RAGFLOW_CACHE_TTL_S", 300.0),
            case_top_k=_get_int("CASE_TOP_K", 3),
            case_candidate_k=_get_int("CASE_CANDIDATE_K", 10),
            case_min_similarity=_get_float("CASE_MIN_SIMILARITY", 0.1),
            pattern_candidate_k=_get_int("PATTERN_CANDIDATE_K", 4),
            pattern_min_similarity=_get_float("PATTERN_MIN_SIMILARITY", 0.25),
            negative_candidate_k=_get_int("NEGATIVE_CANDIDATE_K", 4),
            negative_min_similarity=_get_float("NEGATIVE_MIN_SIMILARITY", 0.25),
            case_snapshot_dir=os.getenv("CASE_SNAPSHOT_DIR", "data/case_snapshots"),
            upstream_base_url=os.getenv("UPSTREAM_BASE_URL", ""),
            upstream_api_key=os.getenv("UPSTREAM_API_KEY", ""),
            upstream_timeout_s=_get_float("UPSTREAM_TIMEOUT_S", 3.0),
            internal_token=os.getenv("MC_INTERNAL_TOKEN", ""),
            max_calls_per_session=_get_int("MAX_CALLS_PER_SESSION", 12),
            cost_budget_cny=_get_float("COST_BUDGET_CNY", 0.08),
            min_rounds=_get_int("MIN_ROUNDS", 2),
            max_rounds=_get_int("MAX_ROUNDS", 3),
            escalate_confidence=_get_float("ESCALATE_CONFIDENCE", 0.8),
            prefetch=_get_bool("PREFETCH", True),
            items_per_session=_get_int("ITEMS_PER_SESSION", 3),
        )

    def use_mock_llm(self) -> bool:
        return self.llm_provider.strip().lower() == "mock"


DEFAULT_SETTINGS = Settings.from_env()
