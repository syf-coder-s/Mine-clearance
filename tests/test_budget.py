"""预算守卫：12 次上限必须靠异常守住，而不是靠自觉。"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mineclearance.budget import STAGE_LIMITS, BudgetExceeded, CallBudget  # noqa: E402


def spend(budget: CallBudget, stage: str, times: int) -> None:
    for _ in range(times):
        budget.check(stage)
        budget.record(stage, "reasoning", "mock", 10, 0.0)


class StageLimitTest(unittest.TestCase):
    def test_stage_limits_fit_inside_the_hard_cap(self):
        # 申报表写的是 12 次。四个阶段的上限加起来不超过它，多出来的才算余量。
        self.assertLessEqual(sum(STAGE_LIMITS.values()), 12)

    def test_adversary_stops_at_nine(self):
        budget = CallBudget()
        spend(budget, "adversary", 9)
        with self.assertRaises(BudgetExceeded) as caught:
            budget.check("adversary")
        self.assertEqual(caught.exception.stage, "adversary")

    def test_settlement_can_only_run_once(self):
        budget = CallBudget()
        spend(budget, "judge_decision", 1)
        with self.assertRaises(BudgetExceeded):
            budget.check("judge_decision")

    def test_escalation_limited_to_one(self):
        budget = CallBudget()
        spend(budget, "judge_escalation", 1)
        with self.assertRaises(BudgetExceeded):
            budget.check("judge_escalation")

    def test_unregistered_stage_is_rejected_before_spending(self):
        budget = CallBudget()
        with self.assertRaises(BudgetExceeded) as caught:
            budget.check("free_chat")
        self.assertEqual(caught.exception.stage, "free_chat")
        self.assertEqual(budget.total, 0)


class TotalCapTest(unittest.TestCase):
    def test_total_cap_wins_over_generous_stage_limits(self):
        budget = CallBudget(cap=2, cost_cap_cny=99.0, stage_limits={"adversary": 5, "report": 1})
        spend(budget, "adversary", 2)
        with self.assertRaises(BudgetExceeded) as caught:
            budget.check("report")
        self.assertIn("硬上限", str(caught.exception))
        self.assertEqual(budget.remaining, 0)

    def test_cost_cap(self):
        budget = CallBudget(cap=12, cost_cap_cny=0.01)
        budget.check("report")
        budget.record("report", "decision", "mock", 5, 0.02)
        with self.assertRaises(BudgetExceeded) as caught:
            budget.check("adversary")
        self.assertIn("成本", str(caught.exception))

    def test_summary_is_accountable(self):
        budget = CallBudget()
        spend(budget, "adversary", 3)
        budget.record("report", "decision", "mock", 20, 0.001)
        self.assertEqual(budget.total, 4)
        self.assertEqual(budget.remaining, 8)
        self.assertEqual(budget.stage_calls(), {"adversary": 3, "report": 1})
        self.assertEqual(budget.latency_ms, 50)
        self.assertAlmostEqual(budget.cost_cny, 0.001)


if __name__ == "__main__":
    unittest.main()
