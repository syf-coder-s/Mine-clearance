"""离线可用的假模型。

作用只有一个：让整条链在没有密钥、没有网络的情况下跑通，
并且把「决策层置信度不足就升级」这条路径也走一遍。
延迟与成本是模拟值，不代表真实调用。
"""

from __future__ import annotations

import json
import re
from typing import List, Sequence

from ..schemas import DefectType, JudgeLabel, Level
from .base import LLMResponse, Message, TokenCallback

_TASK_RE = re.compile(r"TASK=([a-z_]+)")
_ROUND_RE = re.compile(r"ROUND=(\d+)")
_ITEM_RE = re.compile(r"item_id=([A-Za-z0-9_\-]+)")
_MATERIAL_RE = re.compile(r"原始材料：\n(.*?)\n结束。", re.DOTALL)


class MockLLM:
    """确定性输出，保证同一输入每次结果一致，方便断言。"""

    def __init__(self, name: str = "mock", tier: str = "decision") -> None:
        self.name = name
        self.default_tier = tier
        self.call_count = 0

    def complete(
        self,
        messages: Sequence[Message],
        *,
        tier: str = "decision",
        temperature: float = 0.2,
        on_token: TokenCallback = None,
    ) -> LLMResponse:
        self.call_count += 1
        prompt = "\n".join(m.get("content", "") for m in messages)
        text = self._respond(prompt, tier)
        if on_token is not None:
            for i in range(0, len(text), 12):
                on_token(text[i : i + 12])
        return LLMResponse(
            text=text,
            model=("%s-%s" % (self.name, tier)),
            tier=tier,
            tokens_in=max(1, len(prompt) // 3),
            tokens_out=max(1, len(text) // 3),
            cost_cny=0.0007 if tier == "decision" else 0.0021,
            latency_ms=420 if tier == "decision" else 2100,
        )

    def _respond(self, prompt: str, tier: str) -> str:
        task_match = _TASK_RE.search(prompt)
        task = task_match.group(1) if task_match else "unknown"

        if task == "adversary":
            rnd = _ROUND_RE.search(prompt)
            n = rnd.group(1) if rnd else "1"
            return (
                "第 %s 轮质询：你说这里有缺陷，但只给了结论。"
                "请把三件事分开写：缺陷落在哪一段、什么输入会触发、修完之后行为差在哪。"
                "如果你引用了原文，请给出 evidence_id。" % n
            )

        if task == "builder":
            item = _ITEM_RE.search(prompt)
            tag = item.group(1) if item else "item"
            # 固定的小样例：能跑、有健康标记、带足够多的标识符供抽取表识别。
            return (
                "def pick_nearest(values, target):\n"
                "    # item=%s\n"
                "    if not values:\n"
                "        return None\n"
                "    best = values[0]\n"
                "    for value in values[1:]:\n"
                "        if abs(value - target) <= abs(best - target):\n"
                "            best = value\n"
                "    return best\n"
                "\n"
                "# OK\n" % tag
            )

        if task == "planter":
            material = _MATERIAL_RE.search(prompt)
            original = material.group(1).strip("\n") if material else ""
            # 去掉健康标记（结尾可能没有换行），再把边界比较改坏，雷才算真埋上。
            planted = original.replace("# OK", "").replace(" <= ", " < ")
            if not original or planted == original:
                planted = original + "\n# 已改动\n"
            return json.dumps(
                {
                    "planted": planted,
                    "diff": "把边界比较从 <= 改成 <，相等的情况会被漏掉。",
                    "rubric_hint": "能指到比较运算符即可算定位，能说出相等输入才算归因。",
                },
                ensure_ascii=False,
            )

        if task == "judge_decision":
            ids = _ITEM_RE.findall(prompt) or ["unknown"]
            payload = {
                "items": [
                    {
                        "item_id": item_id,
                        "label": JudgeLabel.DEFECT.value,
                        "confidence": 0.64,
                        "note": "抽取表里定位与归因两栏不完整",
                    }
                    for item_id in dict.fromkeys(ids)
                ]
            }
            return json.dumps(payload, ensure_ascii=False)

        if task == "judge_escalation":
            return json.dumps(
                {
                    "label": JudgeLabel.DEFECT.value,
                    "level": Level.L3.value,
                    "rationale": "学生指出了缺陷与触发条件，但没有给出可执行的修复，按 L3 计。",
                },
                ensure_ascii=False,
            )

        if task == "report":
            return (
                "## 本次排雷记录\n\n"
                "三段对抗已完成，判级见上方结算表。\n"
                "下一步建议：把「触发条件」写完整，再补一行可执行的修复。\n"
            )

        return "MOCK:" + task


class EchoLLM:
    """排障用的最小实现：原样回显最后一条用户消息。"""

    def __init__(self) -> None:
        self.name = "echo"

    def complete(
        self,
        messages: Sequence[Message],
        *,
        tier: str = "decision",
        temperature: float = 0.2,
        on_token: TokenCallback = None,
    ) -> LLMResponse:
        text = messages[-1].get("content", "") if messages else ""
        if on_token is not None:
            on_token(text)
        return LLMResponse(
            text=text,
            model="echo",
            tier=tier,
            tokens_in=len(text) // 3,
            tokens_out=len(text) // 3,
            cost_cny=0.0,
            latency_ms=1,
        )
