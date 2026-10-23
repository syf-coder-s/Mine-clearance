"""Web 状态机：不装 fastapi 也能测的那一半。

这里断言的是「发给学生的东西里没有答案」和「会话是单向的」，
不是「HTTP 路由通不通」。后者要真启动服务，属于联调的事。
一条完整会话跑一遍，其余用例在独立 store 上做局部断言，互不污染。
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mineclearance.api.store import (  # noqa: E402
    Sealed,
    SessionClosed,
    SessionNotFound,
    SessionStore,
    StoreError,
    UnknownItem,
    default_specs,
)
from mineclearance.config import Settings  # noqa: E402

ANSWER = (
    "缺陷在 abs(value - target) <= abs(best - target) 这一行，values 里有等距候选时后者覆盖前者。"
    "触发条件是存在两个距离相等的候选。应改为严格小于。"
)


def make_store(**kwargs) -> SessionStore:
    return SessionStore(Settings(llm_provider="mock"), **kwargs)


def play_item(store: SessionStore, session_id: str, item_id: str, rounds: int = 3) -> None:
    for _ in range(rounds):
        store.submit(session_id, item_id, ANSWER, cited=())


def walk_keys(node, acc=None) -> set:
    """递归收集所有字典键名。"""
    acc = set() if acc is None else acc
    if isinstance(node, dict):
        for key, value in node.items():
            acc.add(key)
            walk_keys(value, acc)
    elif isinstance(node, (list, tuple)):
        for child in node:
            walk_keys(child, acc)
    return acc


class LeakTest(unittest.TestCase):
    """开局响应里不能有原版、不能有改动说明、不能有 rubric。"""

    @classmethod
    def setUpClass(cls) -> None:
        cls.store = make_store()
        cls.opened = cls.store.open()

    def test_payload_keys_are_a_whitelist(self):
        item = self.opened["items"][0]
        self.assertEqual(
            set(item),
            {"item_id", "language", "title", "code", "rounds_done", "target_rounds", "evidence"},
        )

    def test_answer_material_is_not_in_the_payload(self):
        # 按**键名**判断，不做全文子串搜索：'verified' 会命中 'unverified_items'，
        # 子串匹配分不清「字段名」和「词根」，那种断言既会误报也会漏报。
        forbidden = {
            "original",
            "diff",
            "rubric_hint",
            "expected_level",
            "anchor",
            "verified",
            "defect",
            "answer",
        }
        leaked = sorted(forbidden & walk_keys(self.opened))
        self.assertEqual(leaked, [], "开局响应里出现了只该在服务端存在的字段: %s" % leaked)

        # 键名漏了还有第二道：原版的正确写法与健康标记都不该出现在整包任何位置。
        dumped = repr(self.opened)
        self.assertNotIn("<=", dumped, "原版代码的正确写法出现在开局响应里")
        self.assertNotIn("# OK", dumped, "出题时的健康标记出现在开局响应里")

    def test_code_is_the_planted_version(self):
        # Mock 出题带 "# OK"，埋雷会把标记去掉并改坏比较，所以开局代码里两者都不对。
        code = self.opened["items"][0]["code"]
        self.assertNotIn("# OK", code, "发给学生的是原版代码，雷没埋")
        self.assertIn("abs(value - target) < abs(best - target)", code)

    def test_evidence_excerpt_never_shows_the_correct_line(self):
        # 证据片段取自原版。只要这段字在埋雷版里看不到，就不能回显，
        # 否则等于把「<= 应该是 <」直接告诉学生。这条比任何 UI 约定都硬。
        for item in self.opened["items"]:
            for evidence in item["evidence"]:
                if evidence["visible_in_code"]:
                    self.assertIn(evidence["excerpt"], item["code"])
                else:
                    self.assertEqual(
                        evidence["excerpt"], "", "不可见的证据连一个字都不能回显，只能给编号"
                    )
                self.assertNotIn("<=", evidence["excerpt"], "证据片段回显了原版的正确写法")

    def test_evidence_is_citable_before_it_is_readable(self):
        # 开局只给编号不给原文，但编号必须真能引用——否则学生无从「用证据说话」。
        evidence_id = self.opened["items"][0]["evidence"][0]["evidence_id"]
        span = self.store.evidence(evidence_id, session_id=self.opened["session_id"])
        self.assertTrue(span["quote"])

    def test_evidence_ids_are_still_offered_for_citation(self):
        items = self.opened["items"]
        self.assertTrue(all(item["evidence"] for item in items), "每题都必须有可引用的证据")


class FlowTest(unittest.TestCase):
    def setUp(self) -> None:
        self.store = make_store()
        self.opened = self.store.open()
        self.session_id = self.opened["session_id"]

    def test_submit_returns_a_challenge_and_costs_one_call(self):
        payload = self.store.submit(self.session_id, "item-1", ANSWER, cited=())
        self.assertTrue(payload["accepted"])
        self.assertEqual(payload["round"], 1)
        self.assertTrue(payload["challenge"])
        self.assertEqual(payload["budget"]["total"], 1)
        self.assertFalse(payload["finished"])

    def test_round_target_stops_the_loop(self):
        play_item(self.store, self.session_id, "item-1", rounds=2)
        payload = self.store.submit(self.session_id, "item-1", ANSWER)
        self.assertFalse(payload["accepted"])
        self.assertEqual(payload["reason"], "target_reached")
        self.assertEqual(payload["rounds_done"], payload["target_rounds"])

    def test_unknown_item_and_unknown_session_are_distinguishable(self):
        with self.assertRaises(UnknownItem) as wrong_item:
            self.store.submit(self.session_id, "item-99", ANSWER)
        self.assertEqual(wrong_item.exception.status, 404)
        with self.assertRaises(SessionNotFound):
            self.store.submit("s_nope", "item-1", ANSWER)

    def test_empty_answer_is_rejected_before_spending(self):
        with self.assertRaises(StoreError) as caught:
            self.store.submit(self.session_id, "item-1", "   ")
        self.assertEqual(caught.exception.status, 400)
        self.assertEqual(self.store.state(self.session_id)["budget"]["total"], 0, "空作答不该花钱")

    def test_session_is_one_way(self):
        play_item(self.store, self.session_id, "item-1", rounds=2)
        self.store.settle(self.session_id)
        with self.assertRaises(SessionClosed):
            self.store.settle(self.session_id)
        with self.assertRaises(SessionClosed):
            self.store.submit(self.session_id, "item-1", ANSWER)

    def test_state_reports_rounds_without_spending(self):
        play_item(self.store, self.session_id, "item-2", rounds=1)
        before = self.store.state(self.session_id)["budget"]["total"]
        state = self.store.state(self.session_id)
        item = next(i for i in state["items"] if i["item_id"] == "item-2")
        self.assertEqual(item["rounds_done"], 1)
        self.assertEqual(state["budget"]["total"], before)

    def test_closed_session_is_gone(self):
        self.store.close(self.session_id)
        with self.assertRaises(SessionNotFound):
            self.store.state(self.session_id)
        with self.assertRaises(SessionNotFound):
            self.store.close(self.session_id)


class FullSessionTest(unittest.TestCase):
    """一场完整的 Web 会话：三段题、结算、复盘。"""

    @classmethod
    def setUpClass(cls) -> None:
        cls.store = make_store()
        cls.opened = cls.store.open(default_specs(3))
        cls.session_id = cls.opened["session_id"]
        for item in cls.opened["items"]:
            for _ in range(item["target_rounds"]):
                cls.store.submit(cls.session_id, item["item_id"], ANSWER)
        cls.report = cls.store.settle(cls.session_id)

    def test_online_calls_stay_inside_the_cap(self):
        self.assertLessEqual(self.report["calls"], self.report["budget"]["cap"])
        self.assertEqual(self.report["calls"], self.report["budget"]["total"])

    def test_stage_distribution_is_explainable_from_the_web_path(self):
        stages = self.report["stage_calls"]
        self.assertEqual(stages.get("judge_decision", 0), 1)
        self.assertLessEqual(stages.get("judge_escalation", 0), 1)
        self.assertEqual(stages.get("report", 0), 1)
        self.assertEqual(self.report["calls"], sum(stages.values()))

    def test_verdicts_come_with_references_only_after_settlement(self):
        self.assertTrue(self.report["verdicts"])
        for verdict in self.report["verdicts"]:
            for evidence_id in verdict["citation"]["supported"]:
                reference = next(r for r in verdict["references"] if r["evidence_id"] == evidence_id)
                self.assertTrue(reference["quote"], "已结算的引用应当能取回原文")
            self.assertIn(
                verdict["level"],
                {
                    "L0_false_alarm",
                    "L1_perception",
                    "L2_localization",
                    "L3_attribution",
                    "L4_repair",
                },
            )

    def test_report_has_a_human_readable_part(self):
        self.assertTrue(self.report["markdown"].strip())
        self.assertEqual(self.report["unverified_items"], 0)
        self.assertTrue(self.report["trace"], "调用轨迹要能解释这 11 次花在哪")


class RagProxyTest(unittest.TestCase):
    """预留的检索代理：会话内已被封印，建库通道仍可用。"""

    def setUp(self) -> None:
        self.store = make_store()
        self.opened = self.store.open()
        self.session_id = self.opened["session_id"]

    def test_session_scoped_retrieve_is_refused_after_seal(self):
        with self.assertRaises(Sealed) as caught:
            self.store.retrieve("再查一次", top_k=3, session_id=self.session_id)
        self.assertEqual(caught.exception.status, 409)

    def test_bank_scope_is_open_for_offline_building(self):
        payload = self.store.retrieve("alpha", top_k=3)
        self.assertEqual(payload["scope"], "bank")
        self.assertFalse(payload["sealed"])
        self.assertEqual(payload["items"], [], "建库通道此时还没写入任何文档")

    def test_evidence_proxy_returns_the_sealed_span(self):
        evidence_id = self.opened["items"][0]["evidence"][0]["evidence_id"]
        span = self.store.evidence(evidence_id, session_id=self.session_id)
        self.assertEqual(span["evidence_id"], evidence_id)
        self.assertTrue(span["quote"])
        self.assertEqual(len(span["quote"]), span["char_end"] - span["char_start"])


class TtlTest(unittest.TestCase):
    def test_idle_sessions_are_recycled(self):
        now = [1000.0]
        store = make_store(ttl_s=60.0, clock=lambda: now[0])
        opened = store.open()
        now[0] += 61.0
        store.open()  # 触发清理
        with self.assertRaises(SessionNotFound):
            store.state(opened["session_id"])


if __name__ == "__main__":
    unittest.main()
