"""数据契约：冻结、校验、可序列化。

这些字段是对外承诺（前端、题库、评测脚本都按它读），所以校验必须在这里抛错，
而不是等到结算时才发现 quote 和区间对不上。
"""

from __future__ import annotations

import json
import sys
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mineclearance.schemas import (  # noqa: E402
    DefectItem,
    DefectType,
    EvidenceSpan,
    ItemSpec,
    JudgeLabel,
    Level,
    StudentAnswer,
    to_dict,
)


def span(**overrides) -> EvidenceSpan:
    fields = dict(
        evidence_id="ev_1",
        doc_id="doc_1",
        chunk_id="doc_1#0-10",
        char_start=0,
        char_end=10,
        quote="0123456789",
    )
    fields.update(overrides)
    return EvidenceSpan(**fields)


def item(**overrides) -> DefectItem:
    fields = dict(
        item_id="item-1",
        language="python",
        defect_type=DefectType.BOUNDARY,
        title="最接近目标值的元素",
        original="def f(v):\n    return v\n",
        planted="def f(v):\n    return v[0]\n",
        diff="-    return v\n+    return v[0]",
        evidence_ids=("ev_1",),
        expected_level=Level.L2,
        verified=True,
    )
    fields.update(overrides)
    return DefectItem(**fields)


class SpanTest(unittest.TestCase):
    def test_quote_must_match_the_range(self):
        # 引用核验靠「quote 就是原文这一段」成立，长度对不上就没法核验。
        with self.assertRaises(ValueError):
            span(char_end=11)

    def test_illegal_range(self):
        with self.assertRaises(ValueError):
            span(char_start=5, char_end=5, quote="")
        with self.assertRaises(ValueError):
            span(char_start=-1, char_end=4, quote="0123")

    def test_empty_evidence_id(self):
        with self.assertRaises(ValueError):
            span(evidence_id="")

    def test_frozen(self):
        with self.assertRaises(FrozenInstanceError):
            span().doc_id = "doc_2"


class ItemTest(unittest.TestCase):
    def test_planted_must_differ(self):
        with self.assertRaises(ValueError):
            item(planted="def f(v):\n    return v\n")

    def test_must_carry_evidence(self):
        # 没有证据的雷不可核验，学生引用也就无从谈起。
        with self.assertRaises(ValueError):
            item(evidence_ids=())

    def test_fingerprint_tracks_content(self):
        base = item()
        self.assertEqual(base.fingerprint(), item().fingerprint())
        self.assertNotEqual(base.fingerprint(), item(planted="def f(v):\n    return v[-1]\n").fingerprint())
        self.assertEqual(len(base.fingerprint()), 16)

    def test_spec_fingerprint_tracks_intent(self):
        spec = ItemSpec(
            item_id="item-1",
            topic="边界比较",
            language="python",
            defect_type=DefectType.BOUNDARY,
            expected_level=Level.L2,
        )
        same = ItemSpec(
            item_id="item-1",
            topic="边界比较",
            language="python",
            defect_type=DefectType.BOUNDARY,
            expected_level=Level.L2,
        )
        other = ItemSpec(
            item_id="item-1",
            topic="边界比较",
            language="python",
            defect_type=DefectType.LOGIC,
            expected_level=Level.L2,
        )
        self.assertEqual(spec.fingerprint(), same.fingerprint())
        self.assertNotEqual(spec.fingerprint(), other.fingerprint())


class AnswerTest(unittest.TestCase):
    def test_blank_answer_rejected(self):
        with self.assertRaises(ValueError):
            StudentAnswer(text="   \n ")

    def test_confidence_bounds(self):
        from mineclearance.schemas import CitationReport, Verdict

        with self.assertRaises(ValueError):
            Verdict(
                item_id="item-1",
                label=JudgeLabel.DEFECT,
                level=Level.L3,
                confidence=1.2,
                escalated=False,
                rationale="",
                citation=CitationReport(precision=0.0, recall=0.0),
            )


class SerializationTest(unittest.TestCase):
    def test_to_dict_is_json_ready(self):
        payload = to_dict(item())
        self.assertEqual(payload["defect_type"], "boundary")
        self.assertEqual(payload["expected_level"], "L2_localization")
        self.assertIsInstance(payload["evidence_ids"], list)
        json.dumps(payload, ensure_ascii=False)  # 前端直接吃，不能有非 JSON 类型


if __name__ == "__main__":
    unittest.main()
