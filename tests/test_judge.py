"""裁判的两件纯逻辑：抽取表怎么定级、引用怎么核验。

这两件事都不花调用，所以可以断言得很硬。抽取表那一行是「决策层只吃结构化表」
这句话的落点：如果哪天有人往里塞学生原文，下面的白名单断言会先响。
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mineclearance.agents import citation_report, extract_row  # noqa: E402
from mineclearance.schemas import (  # noqa: E402
    DefectItem,
    DefectType,
    Level,
    RoundRecord,
    StudentAnswer,
)

ORIGINAL = (
    "def closest(values, target):\n"
    "    best = values[0]\n"
    "    for value in values:\n"
    "        if abs(value - target) <= abs(best - target):\n"
    "            best = value\n"
    "    return best\n"
)


def make_item() -> DefectItem:
    return DefectItem(
        item_id="item-1",
        language="python",
        defect_type=DefectType.BOUNDARY,
        title="最接近目标值的元素",
        original=ORIGINAL,
        planted=ORIGINAL.replace(" <= ", " < "),
        diff="- <= \n+ <",
        evidence_ids=("ev_1",),
        expected_level=Level.L2,
        verified=True,
    )


def rounds(*texts: str, fix: str = "") -> tuple:
    return tuple(
        RoundRecord(index=i + 1, answer=StudentAnswer(text=t, proposed_fix=fix), challenge="")
        for i, t in enumerate(texts)
    )


class ExtractRowTest(unittest.TestCase):
    def test_row_is_a_closed_table_not_prose(self):
        row = extract_row(make_item(), rounds("values 在边界处取错了，应改为严格小于"))
        self.assertEqual(
            set(row),
            {
                "item_id",
                "defect_type",
                "rounds",
                "location_hit",
                "trigger_hit",
                "fix_hit",
                "cited",
                "derived_level",
            },
        )

    def test_no_localization_is_l1(self):
        row = extract_row(make_item(), rounds("这段代码看起来有问题"))
        self.assertEqual(row["derived_level"], Level.L1.value)
        self.assertFalse(row["location_hit"])

    def test_localization_without_trigger_is_l2(self):
        row = extract_row(make_item(), rounds("问题出在 values 这个参数上"))
        self.assertEqual(row["derived_level"], Level.L2.value)

    def test_trigger_without_fix_is_l3(self):
        row = extract_row(make_item(), rounds("values 在边界处取错了，两个候选取了后一个"))
        self.assertEqual(row["derived_level"], Level.L3.value)

    def test_fix_promotes_to_l4(self):
        row = extract_row(make_item(), rounds("values 在边界处取错了，应改为严格小于"))
        self.assertEqual(row["derived_level"], Level.L4.value)

    def test_proposed_fix_alone_counts_as_fix(self):
        row = extract_row(make_item(), rounds("values 在边界处取错了", fix="把 <= 改成 <"))
        self.assertTrue(row["fix_hit"])
        self.assertEqual(row["derived_level"], Level.L4.value)

    def test_only_the_last_round_is_judged(self):
        # 前几轮写得再全也不算数：判的是「最后一次提交到什么程度」。
        row = extract_row(
            make_item(),
            rounds("values 在边界处错了，应改为严格小于", "不知道"),
        )
        self.assertEqual(row["rounds"], 2)
        self.assertEqual(row["derived_level"], Level.L1.value)

    def test_citations_come_from_the_last_round(self):
        records = (
            RoundRecord(1, StudentAnswer(text="values 边界", cited_evidence_ids=("ev_1",)), ""),
            RoundRecord(2, StudentAnswer(text="values 边界", cited_evidence_ids=("ev_2",)), ""),
        )
        self.assertEqual(extract_row(make_item(), records)["cited"], ["ev_2"])


class CitationReportTest(unittest.TestCase):
    def test_fabricated_ids_are_unsupported_not_missing(self):
        report = citation_report(["ev_1", "ev_fake"], ["ev_1", "ev_2"])
        self.assertEqual(report.supported, ("ev_1",))
        self.assertEqual(report.unsupported, ("ev_fake",))
        self.assertEqual(report.missing, ("ev_2",))
        self.assertAlmostEqual(report.precision, 0.5)
        self.assertAlmostEqual(report.recall, 0.5)

    def test_no_citation_means_zero_precision_not_full_marks(self):
        report = citation_report([], ["ev_1"])
        self.assertEqual(report.precision, 0.0)
        self.assertEqual(report.recall, 0.0)
        self.assertEqual(report.missing, ("ev_1",))

    def test_duplicates_are_collapsed(self):
        report = citation_report(["ev_1", "ev_1"], ["ev_1"])
        self.assertEqual(report.supported, ("ev_1",))
        self.assertAlmostEqual(report.precision, 1.0)


if __name__ == "__main__":
    unittest.main()
