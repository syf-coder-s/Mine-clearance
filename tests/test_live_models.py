"""验证接入的关键边界，不请求付费服务。"""
import io
import json
import unittest
from unittest.mock import patch

from mineclearance.agents.pure_probe import PurePythonProbe
from mineclearance.budget import CallBudget
from mineclearance.config import Settings
from mineclearance.llm import build_router
from mineclearance.llm.openai_compat import OpenAICompatLLM
from tests.test_vendor_isolation import judge_with, make_run, FULL_ANSWER
from mineclearance.schemas import JudgeLabel, Level
from mineclearance.agents import Adversary
from mineclearance.rag import LocalStubRAG, SealedView
from tests.test_vendor_isolation import ScriptedLLM
from mineclearance.llm import Router

SOURCE = 'def nearest(xs, target):\n    return min(xs, key=lambda x: abs(x-target)) if xs else None\n'
TESTS = '''def test_nearest():
    assert nearest([], 2) is None
    assert nearest([1, 3], 2) == 1
    assert nearest([1, 4], 3) == 4
'''


class LiveModelsTest(unittest.TestCase):
    def test_mimo_auth_and_builder_route(self):
        settings = Settings(llm_provider="real", llm_api_base="https://api.deepseek.com",
            decision_model="deepseek-flash", reasoning_model="deepseek-v4-pro",
            builder_api_base="https://api.xiaomimimo.com/v1", builder_model="mimo-v2.6-flash",
            builder_auth_header="api-key", builder_api_key="test-only",
            adversary_api_base="https://api.xiaomimimo.com/v1", adversary_auth_header="api-key")
        router = build_router(settings)
        client = router.client_for("builder")
        self.assertEqual(client._headers()["api-key"], "test-only")
        self.assertNotIn("Authorization", client._headers())
        self.assertTrue(router.vendor_isolated)
        self.assertEqual(router.summary()["model_routes"]["builder"], "mimo-v2.6-flash")
        self.assertEqual(router.summary()["model_routes"]["planter"], "deepseek-v4-pro")

    def test_same_host_does_not_claim_vendor_isolation(self):
        self.assertFalse(build_router(Settings(llm_provider="real", llm_api_base="https://same.example/v1",
                                               adversary_api_base="https://same.example/other")).vendor_isolated)

    def test_stream_usage_in_final_empty_choice_event(self):
        events = [dict(choices=[dict(delta=dict(content="OK"))]),
                  dict(choices=[], usage=dict(prompt_tokens=10, completion_tokens=3))]
        stream = io.BytesIO(("".join("data: " + json.dumps(e) + "\n\n" for e in events) + "data: [DONE]\n").encode())
        client = OpenAICompatLLM("m", "https://test.example")
        with patch("urllib.request.urlopen", return_value=stream):
            response = client.complete([], on_token=lambda s: None)
        self.assertEqual((response.tokens_in, response.tokens_out), (10, 3))
        self.assertTrue(response.usage_known)
        self.assertFalse(response.cost_known)

    def test_real_behavior_pair(self):
        original, planted = PurePythonProbe().verify_pair(SOURCE, SOURCE.replace("min(", "max("), TESTS)
        self.assertTrue(original.ok, original.detail)
        self.assertFalse(planted.ok)
        self.assertIn("AssertionError", planted.detail)

    def test_missing_tests_and_syntax_errors_are_rejected(self):
        probe = PurePythonProbe()
        self.assertFalse(probe.verify_pair(SOURCE, "def broken(:", TESTS)[0].ok)
        self.assertFalse(probe.verify_pair(SOURCE, SOURCE.replace("min(", "max("), "")[0].ok)

    def test_io_and_test_override_are_rejected(self):
        probe = PurePythonProbe()
        for bad in ["def nearest(xs, t):\n    return open('secret').read()",
                    "import os\ndef nearest(xs, t):\n    return 1"]:
            self.assertFalse(probe.verify_pair(SOURCE, bad, TESTS)[0].ok)
        bad_tests = TESTS.replace("def test_nearest", "def nearest")
        self.assertFalse(probe.verify_pair(SOURCE, SOURCE.replace("min(", "max("), bad_tests)[0].ok)

    def test_escalation_updates_label_and_rejects_invalid_level(self):
        decision = '{"items":[{"item_id":"item-1","label":"defect_present","confidence":0.5}]}'
        judge = judge_with(decision, '{"label":"no_defect","level":"L0_false_alarm","rationale":"误报"}')
        verdict = judge.settle((make_run(FULL_ANSWER),), budget=CallBudget())[0]
        self.assertEqual(verdict.label, JudgeLabel.NONE)
        self.assertEqual(verdict.level, Level.L0)
        judge = judge_with(decision, '{"label":"nonsense","level":"L9","rationale":"无效"}')
        self.assertFalse(judge.settle((make_run(FULL_ANSWER),), budget=CallBudget())[0].escalated)

    def test_adversary_cannot_see_correct_only_code(self):
        from dataclasses import replace
        item = make_run(FULL_ANSWER).item
        rag = LocalStubRAG()
        rag.index("doc", item.original, language="python")
        ids = tuple(c.evidence_id for c in rag.retrieve("code", top_k=3, doc_id="doc"))
        item = replace(item, evidence_ids=ids)
        rag.seal()
        client = ScriptedLLM("请补充反例", "adv")
        router = Router({"adversary": client})
        Adversary(router).challenge(item, make_run(FULL_ANSWER).rounds[0].answer, 1,
                                   budget=CallBudget(), view=SealedView(rag))
        prompt = client.prompts[0][-1]["content"]
        self.assertIn(item.planted, prompt)
        self.assertNotIn(item.original, prompt)

    def test_judge_prompt_does_not_contain_target_level(self):
        judge = judge_with('{"items": []}')
        run = make_run(FULL_ANSWER)
        judge._escalate(run.item.item_id, [run], [], CallBudget(), None)
        prompt = judge.router.client_for("reasoning").prompts[0][-1]["content"]
        self.assertNotIn("期望等级=", prompt)


if __name__ == "__main__":
    unittest.main()
