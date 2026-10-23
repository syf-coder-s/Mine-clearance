"""裁决层：状态机 / 两段式预算 / 锚点。不装 fastapi 也能跑。

这些用例是给后端同学的验收单：现在打的是 FakeUpstream，接上后端后把
setUp 里的实现换成 HttpUpstream，断言一条都不用改。
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mineclearance.api.store import SessionStore  # noqa: E402
from mineclearance.config import Settings  # noqa: E402
from mineclearance.upstream import (  # noqa: E402
    AnchorForbidden,
    BudgetExhausted,
    FakeUpstream,
    HttpUpstream,
    ReferenceOutOfScope,
    StageConflict,
    UpstreamUnavailable,
    build_upstream,
    error_for_status,
)

SID = "s_test"

ITEMS = [
    {"item_id": "item-1", "doc_id": "doc_item-1", "evidence_ids": ["ev_a", "ev_b"]},
    {"item_id": "item-2", "doc_id": "doc_item-2", "evidence_ids": ["ev_c"]},
]


class StageMachineTest(unittest.TestCase):
    """状态非法一律 409，不存在「静默补默认值」。"""

    def setUp(self) -> None:
        self.up = FakeUpstream()

    def test_missing_stage_is_conflict(self) -> None:
        with self.assertRaises(StageConflict) as ctx:
            self.up.propose_stage(SID, "")
        self.assertEqual(ctx.exception.status, 409)

    def test_unknown_stage_is_conflict(self) -> None:
        with self.assertRaises(StageConflict):
            self.up.propose_stage(SID, "free_chat")

    def test_cannot_jump_straight_to_report(self) -> None:
        with self.assertRaises(StageConflict):
            self.up.propose_stage(SID, "report")

    def test_happy_path_then_terminal(self) -> None:
        self.assertEqual(self.up.propose_stage(SID, "adversary").previous, "open")
        self.up.propose_stage(SID, "adversary")
        self.up.propose_stage(SID, "judge_decision")
        self.up.propose_stage(SID, "judge_escalation")
        self.up.propose_stage(SID, "report")
        with self.assertRaises(StageConflict):
            self.up.propose_stage(SID, "adversary")

    def test_seq_is_monotonic(self) -> None:
        first = self.up.propose_stage(SID, "adversary")
        second = self.up.propose_stage(SID, "adversary")
        self.assertLess(first.seq, second.seq)

    def test_sessions_do_not_share_state(self) -> None:
        self.up.propose_stage(SID, "adversary")
        ticket = self.up.propose_stage("s_other", "adversary")
        self.assertEqual(ticket.previous, "open")


class BudgetTest(unittest.TestCase):
    """先占后花：reserved 占额度，commit 才记账，void 还回去。"""

    def setUp(self) -> None:
        self.up = FakeUpstream()

    def test_reserve_commit_is_single_use(self) -> None:
        reservation = self.up.reserve(SID, "adversary")
        self.assertEqual(reservation.state, "reserved")
        committed = self.up.commit(reservation.reservation_id, cost_cny=0.0012)
        self.assertEqual(committed.state, "committed")
        self.assertAlmostEqual(committed.cost_cny, 0.0012)
        with self.assertRaises(StageConflict):
            self.up.commit(reservation.reservation_id)

    def test_void_frees_the_slot(self) -> None:
        first = self.up.reserve(SID, "report")
        self.up.void(first.reservation_id)
        second = self.up.reserve(SID, "report")
        self.assertNotEqual(first.reservation_id, second.reservation_id)

    def test_stage_limit_is_enforced(self) -> None:
        for _ in range(9):
            self.up.reserve(SID, "adversary")
        with self.assertRaises(BudgetExhausted) as ctx:
            self.up.reserve(SID, "adversary")
        self.assertEqual(ctx.exception.status, 409)

    def test_total_cap_is_enforced(self) -> None:
        small = FakeUpstream(cap=2)
        small.reserve(SID, "adversary")
        small.reserve(SID, "adversary")
        with self.assertRaises(BudgetExhausted):
            small.reserve(SID, "judge_decision")

    def test_missing_stage_cannot_reserve(self) -> None:
        with self.assertRaises(StageConflict):
            self.up.reserve(SID, "")

    def test_unknown_reservation_is_conflict(self) -> None:
        with self.assertRaises(StageConflict):
            self.up.commit("rsv_missing")


class AnchorTest(unittest.TestCase):
    """越权 403、越域 422、seal 后不可增删 409。"""

    def setUp(self) -> None:
        self.up = FakeUpstream()
        self.up.sync_session(SID, ITEMS)

    def test_unknown_session_is_forbidden(self) -> None:
        with self.assertRaises(AnchorForbidden) as ctx:
            self.up.anchor("s_nobody", "item-1")
        self.assertEqual(ctx.exception.status, 403)

    def test_anchor_holds_the_frozen_set(self) -> None:
        anchor = self.up.anchor(SID, "item-1")
        self.assertEqual(anchor.evidence_ids, frozenset({"ev_a", "ev_b"}))
        self.assertEqual(anchor.doc_id, "doc_item-1")
        self.assertTrue(anchor.allows("ev_a"))
        self.assertFalse(anchor.allows("ev_z"))

    def test_anchor_cannot_grow_after_seal(self) -> None:
        with self.assertRaises(StageConflict):
            self.up.sync_session(SID, ITEMS + [{"item_id": "item-3", "doc_id": "doc_item-3", "evidence_ids": ["ev_d"]}])

    def test_anchor_cannot_drop_evidence(self) -> None:
        with self.assertRaises(StageConflict):
            self.up.sync_session(SID, [ITEMS[0], {"item_id": "item-2", "doc_id": "doc_item-2", "evidence_ids": ["ev_c", "ev_d"]}])

    def test_reference_in_scope_passes(self) -> None:
        self.assertEqual(self.up.verify_reference(SID, "item-1", ["ev_a", "ev_b"]), 2)

    def test_reference_out_of_scope_is_422(self) -> None:
        with self.assertRaises(ReferenceOutOfScope) as ctx:
            self.up.verify_reference(SID, "item-1", ["ev_a", "ev_c"])
        self.assertEqual(ctx.exception.status, 422)
        self.assertIn("ev_c", str(ctx.exception))

    def test_verify_on_foreign_item_is_403(self) -> None:
        with self.assertRaises(AnchorForbidden):
            self.up.verify_reference(SID, "item-9", ["ev_a"])


class HttpMappingTest(unittest.TestCase):
    """后端接上后，状态码必须原样落成这四类异常，不能被吞成 500。"""

    def test_status_mapping(self) -> None:
        cases = {
            403: AnchorForbidden,
            409: StageConflict,
            422: ReferenceOutOfScope,
            429: BudgetExhausted,
            500: UpstreamUnavailable,
        }
        for status, kind in cases.items():
            error = error_for_status(status, "detail")
            self.assertIsInstance(error, kind)
            self.assertEqual(error.status, kind.status)

    def test_summary_does_not_call_backend(self) -> None:
        upstream = HttpUpstream("http://127.0.0.1:9", timeout_s=0.01)
        self.assertEqual(upstream.summary()["mode"], "http")
        self.assertFalse(upstream.summary()["degraded"])


class BuildTest(unittest.TestCase):
    def test_default_is_fake(self) -> None:
        self.assertEqual(build_upstream(Settings()).summary()["mode"], "fake")

    def test_configured_base_url_switches_to_http(self) -> None:
        upstream = build_upstream(Settings(upstream_base_url="http://127.0.0.1:9"))
        self.assertEqual(upstream.summary()["mode"], "http")


class StoreAnchorTest(unittest.TestCase):
    """store.anchors() 是壳层与裁决层之间唯一的交接面。"""

    def test_anchors_come_from_the_sealed_session(self) -> None:
        store = SessionStore(Settings(llm_provider="mock"))
        opened = store.open()
        rows = store.anchors(opened["session_id"])
        self.assertTrue(rows)
        for row in rows:
            self.assertEqual(row["doc_id"], "doc_%s" % row["item_id"])
            self.assertTrue(row["evidence_ids"])
        # 锚点里不能有答案侧字段
        for row in rows:
            self.assertNotIn("expected_level", row)
            self.assertNotIn("original", row)


if __name__ == "__main__":
    unittest.main()
