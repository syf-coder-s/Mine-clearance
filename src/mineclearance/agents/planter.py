"""埋雷：把一份正确的材料改成「有一处确定缺陷」的版本。

这里最容易出的问题是「雷埋歪了」——原版也挂了，或者埋完之后根本跑不起来。
所以 plant() 的返回值里 accepted 不是装饰：accepted=False 的题会被主链剔除，
不会拿去判学生。复核在封印之前，用 probe.py 里的探针跑。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from typing import Optional, Sequence

from ..llm import Router, system, user
from ..schemas import DefectItem, ItemSpec
from .probe import Probe, ProbeResult


class PlanterError(RuntimeError):
    pass


@dataclass(frozen=True)
class PlantOutcome:
    item: DefectItem
    accepted: bool
    reason: str
    original_probe: Optional[ProbeResult] = None
    planted_probe: Optional[ProbeResult] = None


class Planter:
    def __init__(self, router: Router, probe: Optional[Probe] = None) -> None:
        self.router = router
        self.probe = probe

    def plant(self, spec: ItemSpec, original: str, evidence_ids: Sequence[str], *, tests: str = "") -> PlantOutcome:
        messages = [
            system(
                "你是埋雷人。给定一段正确的材料，只改一处，制造一个真实存在的缺陷。"
                "只输出 JSON：{\"planted\": \"改后全文\", \"diff\": \"改动说明，一到两句\", "
                "\"rubric_hint\": \"判级提示\"}。不要输出多余文字。"
                "缺陷类型必须与给定的一致；改动必须能在原文里被定位到。"
                "保持函数签名、原文的行为约定和语法合法，只改一处行为；禁止 import、文件、网络、反射。"
            ),
            user(
                "TASK=planter\n"
                "item_id=%s\n"
                "LANGUAGE=%s\n"
                "DEFECT_TYPE=%s\n"
                "原始材料：\n%s\n"
                "结束。"
                % (spec.item_id, spec.language, spec.defect_type.value, original)
            ),
        ]
        response = self.router.offline("planter", messages)
        payload = _parse_json(response.text)
        planted = str(payload.get("planted", "")).strip()
        if not planted:
            raise PlanterError("埋雷返回里没有 planted: %s" % spec.item_id)
        if planted == original.strip():
            raise PlanterError("埋雷版与原版相同，没改: %s" % spec.item_id)

        item = DefectItem(
            item_id=spec.item_id,
            language=spec.language,
            defect_type=spec.defect_type,
            title=spec.topic,
            original=original,
            planted=planted,
            diff=str(payload.get("diff", "")).strip() or "未给出改动说明",
            evidence_ids=tuple(evidence_ids),
            expected_level=spec.expected_level,
            rubric_hint=str(payload.get("rubric_hint", "")).strip(),
            verified=False,
            verify_source="none",
            test_source=tests,
        )

        if self.probe is None:
            return PlantOutcome(item=item, accepted=False, reason="未配置探针，题目不予采用")

        pair = getattr(self.probe, "verify_pair", None)
        pair_results = pair(original, planted, tests) if callable(pair) else None
        original_result = pair_results[0] if pair_results else self.probe.run(original)
        if not original_result.ok:
            return PlantOutcome(
                item=item,
                accepted=False,
                reason="原版自身未通过探针，题目作废",
                original_probe=original_result,
            )

        planted_result = pair_results[1] if pair_results else self.probe.run(planted)
        if planted_result.ok or planted_result.timed_out:
            return PlantOutcome(
                item=item,
                accepted=False,
                reason="埋雷版仍然通过探针，雷没埋上",
                original_probe=original_result,
                planted_probe=planted_result,
            )

        return PlantOutcome(
            item=replace(item, verified=True, verify_source=type(self.probe).__name__),
            accepted=True,
            reason="原版通过、埋雷版失败，复核通过",
            original_probe=original_result,
            planted_probe=planted_result,
        )


def _parse_json(text: str) -> dict:
    """容忍模型在 JSON 前后加话或加围栏。"""
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = stripped.split("\n", 1)[-1]
        if stripped.rstrip().endswith("```"):
            stripped = stripped.rstrip()[:-3]
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start < 0 or end <= start:
        raise PlanterError("埋雷返回不是 JSON: %s" % text[:160])
    try:
        payload = json.loads(stripped[start : end + 1])
    except ValueError as exc:
        raise PlanterError("埋雷返回 JSON 解析失败: %s" % exc) from exc
    if not isinstance(payload, dict):
        raise PlanterError("埋雷返回不是对象")
    return payload
