"""内存版裁决方。

存在意义不是「凑一个能跑的壳」，而是让对接前就能验口径：
    · 状态机的拒绝路径（409）能写单测；
    · 两段式预算的「先占后花」能写单测；
    · 锚点的越权（403）与越域（422）能写单测。
后端接上以后把这些用例原样打到 HttpUpstream 上即可，断言不用改。
"""

from __future__ import annotations

import threading
from typing import Dict, List, Mapping, Optional, Sequence

from ..budget import STAGE_LIMITS
from .base import (
    ALLOWED_TRANSITIONS,
    INITIAL_STAGE,
    Anchor,
    AnchorForbidden,
    BudgetExhausted,
    Reservation,
    StageConflict,
    StageTicket,
    as_anchor_rows,
    is_known_stage,
    scope_error,
    summarize,
    transition_error,
)


class FakeUpstream:
    """单进程内存实现。多副本部署时必须换成 HttpUpstream。"""

    def __init__(
        self,
        *,
        cap: int = 12,
        cost_cap_cny: float = 0.08,
        stage_limits: Optional[Mapping[str, int]] = None,
    ) -> None:
        self.cap = cap
        self.cost_cap_cny = cost_cap_cny
        self.stage_limits: Dict[str, int] = dict(STAGE_LIMITS)
        if stage_limits:
            self.stage_limits.update(stage_limits)
        self._lock = threading.RLock()
        self._anchors: Dict[str, Dict[str, Anchor]] = {}
        self._states: Dict[str, tuple] = {}  # session_id -> (stage, seq)
        self._reservations: Dict[str, Reservation] = {}
        self._seq = 0
        self._next_id = 0

    # ---- 锚点 ----

    def sync_session(self, session_id: str, items: Sequence[Mapping[str, object]]) -> None:
        incoming = {
            row["item_id"]: Anchor(
                session_id=session_id,
                item_id=str(row["item_id"]),
                doc_id=str(row["doc_id"]),
                evidence_ids=frozenset(row["evidence_ids"]),
            )
            for row in as_anchor_rows(items)
        }
        with self._lock:
            known = self._anchors.get(session_id)
            if known is None:
                self._anchors[session_id] = incoming
                return
            if set(known) != set(incoming):
                raise StageConflict("锚点已冻结：会话 %s 的题目集合不允许增删" % session_id)
            for item_id, anchor in incoming.items():
                before = known[item_id]
                if before.doc_id != anchor.doc_id or before.evidence_ids != anchor.evidence_ids:
                    raise StageConflict(
                        "锚点已冻结：题 %s 的证据集合在 seal 之后不能改（要换判例请重新开局）" % item_id
                    )

    def anchor(self, session_id: str, item_id: str) -> Anchor:
        with self._lock:
            session = self._anchors.get(session_id)
            anchor = session.get(item_id) if session else None
        if anchor is None:
            raise AnchorForbidden("越权：会话 %s 无权读取题 %s 的锚点" % (session_id, item_id))
        return anchor

    def verify_reference(self, session_id: str, item_id: str, evidence_ids: Sequence[str]) -> int:
        anchor = self.anchor(session_id, item_id)
        offenders = [e for e in evidence_ids if not anchor.allows(e)]
        if offenders:
            raise scope_error(item_id, offenders)
        return len(list(evidence_ids))

    # ---- 状态机 ----

    def propose_stage(self, session_id: str, stage: str) -> StageTicket:
        if not stage:
            raise StageConflict("缺少 stage：状态必须由裁决方决定，不做默认补全")
        if not is_known_stage(stage):
            raise StageConflict("未登记的阶段: %s" % stage)
        with self._lock:
            previous, _ = self._states.get(session_id, (INITIAL_STAGE, 0))
            allowed = ALLOWED_TRANSITIONS.get(previous, frozenset())
            if stage not in allowed:
                raise transition_error(previous, stage)
            self._seq += 1
            self._states[session_id] = (stage, self._seq)
            return StageTicket(session_id=session_id, stage=stage, previous=previous, seq=self._seq)

    # ---- 两段式预算 ----

    def reserve(self, session_id: str, stage: str, units: int = 1) -> Reservation:
        if not stage:
            raise StageConflict("缺少 stage：预留必须指明是哪个阶段在花额度")
        if not is_known_stage(stage):
            raise StageConflict("未登记的阶段: %s" % stage)
        if units < 1:
            raise StageConflict("预留单位必须 ≥ 1，收到 %d" % units)

        with self._lock:
            live = [r for r in self._reservations.values() if r.session_id == session_id and r.state != "voided"]
            used_total = sum(r.units for r in live)
            used_stage = sum(r.units for r in live if r.stage == stage)
            limit = self.stage_limits.get(stage, 0)
            if used_stage + units > limit:
                raise BudgetExhausted(
                    "阶段 %s 额度不足：已占 %d / 上限 %d，本次要 %d" % (stage, used_stage, limit, units)
                )
            if used_total + units > self.cap:
                raise BudgetExhausted(
                    "会话总额度不足：已占 %d / 上限 %d，本次要 %d" % (used_total, self.cap, units)
                )
            self._next_id += 1
            reservation = Reservation(
                reservation_id="rsv_%04d" % self._next_id,
                session_id=session_id,
                stage=stage,
                units=units,
            )
            self._reservations[reservation.reservation_id] = reservation
            return reservation

    def commit(self, reservation_id: str, cost_cny: float = 0.0) -> Reservation:
        return self._close(reservation_id, "committed", cost_cny)

    def void(self, reservation_id: str) -> Reservation:
        return self._close(reservation_id, "voided", 0.0)

    def _close(self, reservation_id: str, state: str, cost_cny: float) -> Reservation:
        with self._lock:
            current = self._reservations.get(reservation_id)
            if current is None:
                raise StageConflict("没有这张预留单: %s" % reservation_id)
            if current.state != "reserved":
                raise StageConflict(
                    "预留单 %s 已经 %s，不能再次 %s"
                    % (reservation_id, current.state, "commit" if state == "committed" else "void")
                )
            updated = Reservation(
                reservation_id=current.reservation_id,
                session_id=current.session_id,
                stage=current.stage,
                units=current.units,
                state=state,
                cost_cny=round(max(0.0, cost_cny), 6),
            )
            self._reservations[reservation_id] = updated
            return updated

    # ---- 观测 ----

    def summary(self) -> Dict[str, object]:
        with self._lock:
            live = [r for r in self._reservations.values() if r.state != "voided"]
            return summarize(
                "fake",
                extra={
                    "cap": self.cap,
                    "cost_budget_cny": self.cost_cap_cny,
                    "stage_limits": dict(self.stage_limits),
                    "sessions": len(self._anchors),
                    "reserved_units": sum(r.units for r in live if r.state == "reserved"),
                    "committed_units": sum(r.units for r in live if r.state == "committed"),
                },
            )

    def reservations(self, session_id: Optional[str] = None) -> List[Reservation]:
        with self._lock:
            return [
                r
                for r in self._reservations.values()
                if session_id is None or r.session_id == session_id
            ]
