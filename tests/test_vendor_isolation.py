"""两条硬约束的守卫测试：厂商隔离与闭集标签。

这两条都是编排文档里标了「已定」、却最容易在改配置时悄悄失效的东西：
    一 · 对抗方与裁判不得同源（表 9 第七行）。同源时升级复核等于自己查自己，
        判级可信度无从谈起，而这个失效在功能上看不出来——会话照常跑完。
    二 · 判定落闭集、不设「部分正确」（表 5 闸二）。PARTIAL 一旦回来，
        学生看到的就是被闸二明令禁止的那个台阶。

正因两者都不会让测试变红，才要在这里把它们变成会红的断言。
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mineclearance.agents.judge import Judge, _JUDGE_SYSTEM, _parse_decisions  # noqa: E402
from mineclearance.budget import CallBudget  # noqa: E402
from mineclearance.config import Settings  # noqa: E402
from mineclearance.llm import LLMResponse, Router, build_router  # noqa: E402
from mineclearance.schemas import (  # noqa: E402
    DefectItem,
    DefectType,
    ItemRun,
    JudgeLabel,
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

FULL_ANSWER = "values 在边界处取错了，两个候选取了后一个，应改为严格小于"


class ScriptedLLM:
    """返回固定文本的假模型，顺带把收到的 prompt 存下来供断言。"""

    def __init__(self, text: str, name: str = "scripted") -> None:
        self.text = text
        self.name = name
        self.prompts = []

    def complete(self, messages, *, tier="decision", temperature=0.2, on_token=None):
        self.prompts.append(list(messages))
        return LLMResponse(
            text=self.text,
            model=self.name,
            tier=tier,
            tokens_in=1,
            tokens_out=1,
            cost_cny=0.0,
            latency_ms=1,
        )


def make_run(*texts: str) -> ItemRun:
    item = DefectItem(
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
    rounds = tuple(
        RoundRecord(index=i + 1, answer=StudentAnswer(text=t), challenge="")
        for i, t in enumerate(texts)
    )
    return ItemRun(item=item, target_rounds=2, rounds=rounds)


def judge_with(decision_json: str, escalation_json: str = "") -> Judge:
    router = Router(
        {
            "decision": ScriptedLLM(decision_json, "dec"),
            "reasoning": ScriptedLLM(
                escalation_json
                or '{"label": "defect_present", "level": "L3_attribution", "rationale": "复核。"}',
                "reason",
            ),
            "adversary": ScriptedLLM("随便一句质询", "adv"),
        }
    )
    return Judge(router, Settings(llm_provider="mock"))


class VendorIsolationTest(unittest.TestCase):
    def test_mock_mode_uses_three_distinct_clients(self):
        router = build_router(Settings(llm_provider="mock"))
        self.assertIsNot(router.client_for("adversary"), router.client_for("reasoning"))
        self.assertIsNot(router.client_for("adversary"), router.client_for("decision"))
        self.assertTrue(router.vendor_isolated)

    def test_adversary_stage_routes_to_its_own_tier(self):
        # 档位表就是隔离的落点：对抗一旦被派回 reasoning 档，隔离就没了，
        # 而且没有任何功能症状，只有这条断言会先响。
        from mineclearance.llm import STAGE_TIER

        self.assertEqual(STAGE_TIER["adversary"], "adversary")
        self.assertNotEqual(STAGE_TIER["adversary"], STAGE_TIER["judge_escalation"])

    def test_single_vendor_falls_back_but_says_so(self):
        settings = Settings(
            llm_provider="openai_compat",
            llm_api_base="http://gateway.example/v1",
            reasoning_model="reason-model",
        )
        router = build_router(settings)
        self.assertIs(router.client_for("adversary"), router.client_for("reasoning"))
        self.assertFalse(router.vendor_isolated, "只配一家厂商时必须如实标记未隔离")
        self.assertFalse(router.summary()["vendor_isolated"])

    def test_second_vendor_isolates_for_real(self):
        settings = Settings(
            llm_provider="openai_compat",
            llm_api_base="http://gateway.example/v1",
            reasoning_model="reason-model",
            adversary_api_base="http://another.example/v1",
            adversary_model="adv-model",
        )
        router = build_router(settings)
        self.assertTrue(router.vendor_isolated)
        adversary = router.client_for("adversary")
        self.assertIsNot(adversary, router.client_for("reasoning"))
        self.assertEqual(adversary.api_base, "http://another.example/v1")
        self.assertEqual(adversary.model, "adv-model")

    def test_store_exposes_isolation_for_health(self):
        from mineclearance.api.store import SessionStore

        store = SessionStore(Settings(llm_provider="mock"))
        self.assertTrue(store.vendor_isolated())


class ClosedSetLabelTest(unittest.TestCase):
    def test_label_set_has_no_partial(self):
        self.assertEqual({label.value for label in JudgeLabel}, {"defect_present", "no_defect"})

    def test_out_of_domain_label_is_dropped_not_translated(self):
        payload = _parse_decisions(
            '{"items": [{"item_id": "item-1", "label": "partial", "confidence": 0.95}]}'
        )
        self.assertEqual(payload, {}, "越域标签不能被翻译成某个合法标签，只能整条丢弃")

    def test_valid_labels_still_pass(self):
        payload = _parse_decisions(
            '{"items": [{"item_id": "item-1", "label": "defect_present", "confidence": 0.9}]}'
        )
        self.assertEqual(payload["item-1"].label, JudgeLabel.DEFECT)

    def test_dropped_decision_falls_back_to_local_table(self):
        judge = judge_with('{"items": [{"item_id": "item-1", "label": "partial", "confidence": 0.9}]}')
        verdicts = judge.settle((make_run(FULL_ANSWER),), budget=CallBudget(), view=None)
        verdict = verdicts[0]
        self.assertEqual(verdict.label, JudgeLabel.DEFECT, "本地兜底按抽取表命中直判")
        self.assertEqual(verdict.confidence, 0.5)
        self.assertIn("抽取表", verdict.rationale)

    def test_local_fallback_can_also_say_no_defect(self):
        # 学生什么都没指出来：抽取表三个命中位全空 → no_defect，不是「部分」。
        judge = judge_with('{"items": []}')
        verdicts = judge.settle((make_run("这段代码看起来不太对劲"),), budget=CallBudget(), view=None)
        self.assertEqual(verdicts[0].label, JudgeLabel.NONE)


class EscalationThresholdTest(unittest.TestCase):
    def test_high_confidence_does_not_escalate(self):
        judge = judge_with(
            '{"items": [{"item_id": "item-1", "label": "defect_present", "confidence": 0.9, "note": "清楚"}]}'
        )
        verdicts = judge.settle((make_run(FULL_ANSWER),), budget=CallBudget(), view=None)
        self.assertFalse(verdicts[0].escalated)
        self.assertEqual(judge.escalations, 0)

    def test_low_confidence_escalates_exactly_once(self):
        judge = judge_with(
            '{"items": [{"item_id": "item-1", "label": "defect_present", "confidence": 0.7, "note": "含糊"}]}'
        )
        verdicts = judge.settle((make_run(FULL_ANSWER),), budget=CallBudget(), view=None)
        self.assertTrue(verdicts[0].escalated)
        self.assertEqual(judge.escalations, 1)
        self.assertEqual(verdicts[0].level, Level.L3)

    def test_prompt_threshold_comes_from_settings(self):
        # 阈值只在 config 出现一次，提示词按它注入。三个数字各写一份正是上次修掉的病。
        settings = Settings(llm_provider="mock", escalate_confidence=0.8)
        router = Router({"decision": ScriptedLLM('{"items": []}', "dec")})
        Judge(router, settings)._decide([], budget=CallBudget())
        prompt = router.client_for("decision").prompts[0][0]["content"]
        self.assertIn("0.80", prompt)
        self.assertNotIn("{threshold", prompt)

    def test_default_threshold_is_the_documented_value(self):
        self.assertEqual(Settings().escalate_confidence, 0.8)
        self.assertNotIn("partial", _JUDGE_SYSTEM)
        self.assertIn("defect_present|no_defect", _JUDGE_SYSTEM)

    def test_escalation_closed_set_is_exactly_the_level_enum(self):
        # 升级层的等级闭集必须与 Level 枚举一字不差：
        # 少一个，模型想判那一档也输出不了；多一个，settle 会在 Level() 处炸。
        import re

        from mineclearance.agents.judge import _ESCALATE_SYSTEM

        closed = set(re.findall(r"L\d_[a-z_]+", _ESCALATE_SYSTEM))
        self.assertEqual(closed, {level.value for level in Level})

    def test_escalation_can_settle_l0_false_alarm(self):
        # L0 只能从升级层进来：闭表结构上判不了误报，这条管子必须是通的。
        judge = judge_with(
            '{"items": [{"item_id": "item-1", "label": "defect_present", "confidence": 0.5, "note": "含糊"}]}',
            '{"label": "defect_present", "level": "L0_false_alarm", "rationale": "所指之处并无该缺陷。"}',
        )
        verdicts = judge.settle((make_run(FULL_ANSWER),), budget=CallBudget(), view=None)
        self.assertEqual(verdicts[0].level, Level.L0)
        self.assertTrue(verdicts[0].escalated)

    def test_table_ladder_never_derives_l0(self):
        # 闭表起步是 L1：三栏全不中只说明「没看出来」，不等于误报，不能推 L0。
        from mineclearance.agents import extract_row

        row = extract_row(make_run("这段代码看起来不太对劲").item, make_run("嗯").rounds)
        self.assertEqual(row["derived_level"], Level.L1.value)
        self.assertNotEqual(row["derived_level"], Level.L0.value)


if __name__ == "__main__":
    unittest.main()
