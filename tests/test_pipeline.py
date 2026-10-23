"""主链：把申报表里承诺的六条变成断言。

一条会话跑一次，其余用例复用它的结果（Mock 模型是确定性的，所以复用的是同一份事实）。
两条 smoke 不好表达的用例单独跑：轮次上限、重复结算、未知题目。
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from typing import Sequence

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mineclearance.agents import MarkerProbe  # noqa: E402
from mineclearance.config import Settings  # noqa: E402
from mineclearance.llm import build_router  # noqa: E402
from mineclearance.orchestration import QuestionBank, Session  # noqa: E402
from mineclearance.rag import IndexSealed, build_retriever  # noqa: E402
from mineclearance.schemas import DefectItem, DefectType, ItemSpec, Level, StudentAnswer  # noqa: E402


class ScriptedAnswers:
    """固定的学生作答：定位、触发条件、修复三段写全，所以抽取表能推到 L4。"""

    def submit(self, item: DefectItem, round_index: int, challenge: str) -> StudentAnswer:
        cited = list(item.evidence_ids[:1])
        if round_index == 1:
            cited.append("ev_deadbeef0000")  # 故意多标一个不存在的证据
        return StudentAnswer(
            text=(
                "缺陷在 abs(value - target) <= abs(best - target) 这一行："
                "等距候选时后者覆盖前者。触发条件是存在两个距离相等的候选。"
                "应改为严格小于，保留先出现的那个。"
            ),
            cited_evidence_ids=tuple(cited),
            proposed_fix="把 <= 改成 <",
        )


def build_specs() -> Sequence[ItemSpec]:
    return (
        ItemSpec(
            item_id="item-1",
            topic="在有序数组里找最接近目标值的元素",
            language="python",
            defect_type=DefectType.BOUNDARY,
            expected_level=Level.L2,
        ),
        ItemSpec(
            item_id="item-2",
            topic="等距候选时的返回值稳定性",
            language="python",
            defect_type=DefectType.LOGIC,
            expected_level=Level.L3,
        ),
        ItemSpec(
            item_id="item-3",
            topic="边界比较运算符的修复",
            language="python",
            defect_type=DefectType.BOUNDARY,
            expected_level=Level.L4,
        ),
    )


def new_session(*, answers=None, bank=None, probe=MarkerProbe()):
    settings = Settings(llm_provider="mock")
    router = build_router(settings)
    retriever = build_retriever(settings)
    session = Session(
        settings=settings,
        router=router,
        retriever=retriever,
        answers=answers,
        bank=bank,
        probe=probe,
    )
    return settings, router, retriever, session


class FullSessionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.settings, cls.router, cls.retriever, cls.session = new_session(
            answers=ScriptedAnswers(), bank=QuestionBank()
        )
        cls.report = cls.session.run(build_specs(), session_id="s_unittest")
        cls.stages = dict(cls.report.stage_calls)

    # ---- 一 · 预算 ----

    def test_online_calls_within_hard_cap(self):
        self.assertLessEqual(self.report.calls, 12)
        self.assertLessEqual(self.report.calls, self.settings.max_calls_per_session)

    def test_stage_distribution_is_explainable(self):
        self.assertLessEqual(self.stages.get("adversary", 0), 9, "对抗阶段越过了留给结算的余量")
        self.assertEqual(self.stages.get("judge_decision", 0), 1, "结算必须有且只有一次决策调用")
        self.assertLessEqual(self.stages.get("judge_escalation", 0), 1, "升级最多一次")
        self.assertEqual(self.stages.get("report", 0), 1, "复盘一次")
        self.assertEqual(self.report.calls, sum(self.stages.values()))

    def test_offline_work_is_counted_but_not_charged_to_the_cap(self):
        self.assertGreater(self.router.offline_calls, 0, "出题与埋雷应该发生离线调用")
        self.assertEqual(self.report.calls, sum(self.stages.values()), "离线调用不能混进在线次数")

    # ---- 二 · 封印 ----

    def test_index_is_sealed_after_open(self):
        self.assertTrue(self.retriever.sealed)
        with self.assertRaises(IndexSealed):
            self.retriever.retrieve("再查一次", top_k=3)
        with self.assertRaises(IndexSealed):
            self.retriever.index("doc_late", "def f():\n    pass\n", language="python")

    def test_evidence_is_read_only_after_seal(self):
        for verdict in self.report.verdicts:
            for evidence_id in verdict.citation.supported:
                self.assertTrue(self.retriever.fetch(evidence_id).quote)

    # ---- 三 · 引用核验 ----

    def test_evidence_never_leaks_across_documents(self):
        # 曾经出过这个错：一题的引用指向另一题的代码。doc_id 作用域是它的回归测试。
        for verdict in self.report.verdicts:
            for evidence_id in verdict.citation.supported:
                span = self.retriever.fetch(evidence_id)
                self.assertEqual(
                    span.doc_id,
                    "doc_" + verdict.item_id,
                    "%s 的引用落在了 %s 里" % (verdict.item_id, span.doc_id),
                )

    def test_every_verdict_cites_sealed_evidence(self):
        self.assertTrue(self.report.verdicts)
        for verdict in self.report.verdicts:
            self.assertGreaterEqual(len(verdict.citation.supported), 1)
            self.assertGreaterEqual(verdict.citation.recall, 0.0)

    # ---- 四 · 结算与报告 ----

    def test_all_accepted_items_are_settled(self):
        self.assertEqual(len(self.report.verdicts), 3)
        self.assertEqual(self.report.unverified_items, 0)
        self.assertEqual(
            sorted(v.item_id for v in self.report.verdicts), ["item-1", "item-2", "item-3"]
        )

    def test_escalation_happens_at_most_once_and_is_reported(self):
        self.assertLessEqual(self.session.judge.escalations, 1)
        self.assertEqual(
            self.session.judge.escalations,
            sum(1 for v in self.report.verdicts if v.escalated),
            "判级里标了已升级，计数就必须对得上",
        )

    def test_report_is_markdown_and_carries_the_numbers(self):
        self.assertTrue(self.report.markdown.strip())
        self.assertEqual(self.report.session_id, "s_unittest")
        self.assertGreaterEqual(self.report.latency_ms, 0)
        self.assertGreaterEqual(self.report.cost_cny, 0.0)

    def test_settling_twice_is_refused(self):
        _, _, _, session = new_session()
        handle = session.open(build_specs(), session_id="s_settle_twice")
        session.settle(handle)
        with self.assertRaises(RuntimeError):
            session.settle(handle)


class RoundControlTest(unittest.TestCase):
    def test_rounds_stop_at_target_and_never_exceed_the_cap(self):
        settings, _, _, session = new_session(answers=ScriptedAnswers())
        handle = session.open(build_specs(), session_id="s_rounds")
        item_id = handle.runs[0].item.item_id
        extra = []
        for _ in range(settings.max_rounds + 1):
            record = session.submit(handle, item_id, ScriptedAnswers().submit(handle.runs[0].item, 1, ""))
            extra.append(record is not None)
        run = next(r for r in handle.runs if r.item.item_id == item_id)
        self.assertLessEqual(len(run.rounds), settings.max_rounds)
        self.assertEqual(len(run.rounds), run.target_rounds)
        self.assertIn(False, extra, "达到目标轮次后应停止追问，而不是继续花调用")

    def test_submit_unknown_item_is_a_keyerror(self):
        _, _, _, session = new_session()
        handle = session.open(build_specs(), session_id="s_unknown")
        with self.assertRaises(KeyError):
            session.submit(handle, "item-404", StudentAnswer(text="随便写点什么"))


class ReuseTest(unittest.TestCase):
    def test_bank_hit_costs_zero_offline_calls(self):
        _, _, _, first = new_session(answers=ScriptedAnswers(), bank=QuestionBank())
        first.run(build_specs(), session_id="s_bank_seed")
        bank = first.bank
        self.assertEqual(len(bank), 3)

        _, router2, _, second = new_session(bank=bank)
        handle = second.open(build_specs(), session_id="s_bank_hit")
        self.assertEqual(router2.offline_calls, 0, "题库命中时不该再出题、再埋雷")
        self.assertEqual(len(handle.runs), 3)

    def test_items_without_probe_evidence_are_never_scored(self):
        _, _, _, session = new_session(probe=None)  # 没有探针 = 无法证明雷埋上了
        handle = session.open(build_specs(), session_id="s_no_probe")
        self.assertEqual(handle.runs, [])
        report = session.settle(handle)
        self.assertEqual(report.verdicts, ())
        self.assertEqual(report.unverified_items, 3)
        self.assertEqual(report.calls, 0, "没有可判的题时不该花任何在线调用")

    def test_empty_recall_is_counted_not_silently_dropped(self):
        # 召回为空的题连 Preparation 都不生成：早先 rejected 按 preparations 数，
        # 这类题会被静默漏掉，账面显示「全通过」。分母必须是出题单总数。
        _, _, _, session = new_session(answers=ScriptedAnswers())

        class BlankBuilder:
            def draft(self, spec):
                return ""  # 空文档 → 切分为空 → 召回为空

        session.builder = BlankBuilder()
        handle = session.open(build_specs(), session_id="s_blank")
        self.assertEqual(handle.runs, [])
        self.assertEqual(handle.rejected, 3, "三张出题单全军覆没，一个都不能少记")


if __name__ == "__main__":
    unittest.main()
