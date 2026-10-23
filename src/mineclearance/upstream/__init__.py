"""裁决层入口。

build_upstream() 是唯一该被调用的构造器：
    配了 UPSTREAM_BASE_URL 就打到后端，没配就用内存实现。
    不要在别处直接 new FakeUpstream——否则预算上限与 config 里的数字会各说各话。
"""

from .base import (
    ALLOWED_TRANSITIONS,
    INITIAL_STAGE,
    Anchor,
    AnchorForbidden,
    BudgetExhausted,
    NotConfigured,
    ReferenceOutOfScope,
    Reservation,
    StageConflict,
    StageTicket,
    Upstream,
    UpstreamFault,
    UpstreamUnavailable,
    anchor_view,
    is_known_stage,
    transition_error,
)
from .fake import FakeUpstream
from .http import HttpUpstream, error_for_status


def build_upstream(settings) -> Upstream:
    if not settings.upstream_base_url:
        return FakeUpstream(
            cap=settings.max_calls_per_session,
            cost_cap_cny=settings.cost_budget_cny,
        )
    return HttpUpstream(
        settings.upstream_base_url,
        settings.upstream_api_key,
        timeout_s=settings.upstream_timeout_s,
    )


__all__ = [
    "Upstream",
    "UpstreamFault",
    "UpstreamUnavailable",
    "NotConfigured",
    "StageConflict",
    "BudgetExhausted",
    "AnchorForbidden",
    "ReferenceOutOfScope",
    "Anchor",
    "StageTicket",
    "Reservation",
    "ALLOWED_TRANSITIONS",
    "INITIAL_STAGE",
    "is_known_stage",
    "transition_error",
    "anchor_view",
    "FakeUpstream",
    "HttpUpstream",
    "error_for_status",
    "build_upstream",
]
