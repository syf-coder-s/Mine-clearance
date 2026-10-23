"""控制面远端契约：状态机 / 两段式预算 / 锚点。

为什么单开一层：
    主链里有三件事不许由 agent 自己说了算——下一步能不能走、这次调用还给不给批、
    这道题冻结了哪些证据。它们归后端裁决，agent 只能提议。这一层就是
    「提议 → 裁决」里那个裁决方的接口。

两种实现，切换只看一个环境变量 UPSTREAM_BASE_URL：
    FakeUpstream  内存实现，七个方法齐全，没接后端也能把端点跑通（默认）。
    HttpUpstream  把同样的语义打到后端，HTTP 状态码直接映射成本层的异常。

一个刻意的取舍：这一层**不降级**。检索挂了可以退到本地桩，因为少一点证据还能继续判；
状态机或预算挂了再退到本地实现，等于一边问后端一边自己说了算——那不是降级，是假装。
所以 HttpUpstream 出错就抛，由壳层翻成 502。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, FrozenSet, List, Mapping, Optional, Protocol, Sequence, runtime_checkable

from ..budget import STAGE_LIMITS

# ---- 错误：状态码与 docs/upstream-api.md 的错误码口径一一对应 ----


class UpstreamFault(RuntimeError):
    """带 HTTP 语义的裁决失败。壳层只按 status 翻译，不猜。"""

    status = 502
    code = "UpstreamFault"


class NotConfigured(UpstreamFault):
    status = 501
    code = "NotConfigured"


class StageConflict(UpstreamFault):
    """状态非法。例：结算之后还想再走一轮对抗。"""

    status = 409
    code = "StageConflict"


class BudgetExhausted(StageConflict):
    """额度不够。仍归 409：这是状态冲突，不是参数错。"""

    code = "BudgetExhausted"


class AnchorForbidden(UpstreamFault):
    """越权取锚点。例：拿 A 会话的凭证读 B 会话的题。"""

    status = 403
    code = "AnchorForbidden"


class ReferenceOutOfScope(UpstreamFault):
    """引用越域。例：上报的 evidence_id 不在这道题的封印集里。"""

    status = 422
    code = "ReferenceOutOfScope"


class UpstreamUnavailable(UpstreamFault):
    status = 502
    code = "UpstreamUnavailable"


# ---- 状态机 ----
#
# 状态名与预算阶段同名，省掉一张映射表：一次「提议」既决定流程走向，
# 也决定这次调用从哪个额度池里扣。
#   open          会话刚开、离线准备已完成、索引已封印
#   adversary     对抗质询（可自循环，每题最多 3 轮）
#   judge_decision 裁判决策档，每题一次
#   judge_escalation 升级复核，每题至多一次
#   report        复盘，一场一次，终态

INITIAL_STAGE = "open"

ALLOWED_TRANSITIONS: Dict[str, FrozenSet[str]] = {
    "open": frozenset({"adversary"}),
    "adversary": frozenset({"adversary", "judge_decision"}),
    "judge_decision": frozenset({"judge_escalation", "report"}),
    "judge_escalation": frozenset({"report"}),
    "report": frozenset(),
}


def is_known_stage(stage: str) -> bool:
    return stage in STAGE_LIMITS


# ---- 数据结构 ----


@dataclass(frozen=True)
class Anchor:
    """一道题在 seal 时刻冻结的证据集合。

    锚点里有「答案侧」信息，只在内部流转：学生可见的 payload 里出现
    `anchor` 这个键就算泄露（tests/test_api_store.py::LeakTest 有禁词断言）。
    """

    session_id: str
    item_id: str
    doc_id: str
    evidence_ids: FrozenSet[str]

    def allows(self, evidence_id: str) -> bool:
        return evidence_id in self.evidence_ids


@dataclass(frozen=True)
class StageTicket:
    """一次被批准的状态转移。seq 是单调序号，便于日志里对齐调用顺序。"""

    session_id: str
    stage: str
    previous: str
    seq: int


@dataclass(frozen=True)
class Reservation:
    """两段式预算的一次预留。

    reserved 期间额度已被占住但未记账；commit 之后才算真正花掉；
    void 把占住的额度还回去。「先占后花」是为了让并发的两条支路
    不会同时看到「还剩 1 次」然后都花掉。
    """

    reservation_id: str
    session_id: str
    stage: str
    units: int = 1
    state: str = "reserved"  # reserved / committed / voided
    cost_cny: float = 0.0


@runtime_checkable
class Upstream(Protocol):
    def sync_session(self, session_id: str, items: Sequence[Mapping[str, object]]) -> None:
        """把本场会话的锚点交给裁决方。首次登记即可，之后必须一字不差。"""

    def propose_stage(self, session_id: str, stage: str) -> StageTicket:
        """提议下一步。不合法就抛 StageConflict，不存在「静默补默认值」。"""

    def reserve(self, session_id: str, stage: str, units: int = 1) -> Reservation: ...

    def commit(self, reservation_id: str, cost_cny: float = 0.0) -> Reservation: ...

    def void(self, reservation_id: str) -> Reservation: ...

    def anchor(self, session_id: str, item_id: str) -> Anchor: ...

    def verify_reference(self, session_id: str, item_id: str, evidence_ids: Sequence[str]) -> int:
        """校验引用是否落在该题锚点内。返回核过的条数，越域抛 422。"""

    def summary(self) -> Dict[str, object]: ...


def transition_error(previous: str, stage: str) -> StageConflict:
    allowed = sorted(ALLOWED_TRANSITIONS.get(previous, frozenset()))
    return StageConflict(
        "状态非法：%s → %s 不允许（%s 之后只允许 %s）"
        % (previous, stage, previous, "、".join(allowed) or "无，已终态")
    )


def scope_error(item_id: str, offenders: Sequence[str]) -> ReferenceOutOfScope:
    return ReferenceOutOfScope(
        "引用越域：%s 不在题 %s 的封印集内（%s）"
        % ("、".join(sorted(offenders)), item_id, "见 /v1/anchor 内部接口")
    )


def as_anchor_rows(items: Sequence[Mapping[str, object]]) -> List[Dict[str, object]]:
    """把 store.anchors() 的行规整成统一形状，两种实现共用。"""
    rows: List[Dict[str, object]] = []
    for item in items:
        evidence_ids = item.get("evidence_ids") or []
        rows.append(
            {
                "item_id": str(item["item_id"]),
                "doc_id": str(item["doc_id"]),
                "evidence_ids": [str(e) for e in evidence_ids],
            }
        )
    return rows


def anchor_view(anchor: Anchor) -> Dict[str, object]:
    """锚点的对外形状。只在内部令牌校验通过后才会被序列化出去。"""
    return {
        "session_id": anchor.session_id,
        "item_id": anchor.item_id,
        "doc_id": anchor.doc_id,
        "evidence_ids": sorted(anchor.evidence_ids),
        "count": len(anchor.evidence_ids),
    }


def summarize(mode: str, *, base_url: str = "", extra: Optional[Mapping[str, object]] = None) -> Dict[str, object]:
    payload: Dict[str, object] = {"mode": mode, "base_url": base_url}
    if extra:
        payload.update(extra)
    return payload
