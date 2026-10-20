"""对抗方：学生每答一轮，就追一次问。

它不是「评分器」，只做一件事——把学生话里没交代清楚的地方顶回去：
缺陷落在哪、什么输入触发、改完行为差在哪、你引的原文是哪一段。
判分不在这里，判分在 judge.py，两边分开是为了让对抗的话术可以放开，
而判分的口径始终锁在封闭集里。
"""

from __future__ import annotations

from typing import Optional, Sequence

from ..llm import Router, system, user
from ..budget import CallBudget
from ..rag import SealedView
from ..schemas import DefectItem, StudentAnswer

_SYSTEM = (
    "你是审稿人，任务是把学生逼到具体。"
    "每一轮只做一件事：指出他这轮回答里最含糊的一处，并要求补一个可核验的细节。"
    "不要给出正确答案，不要说出缺陷在哪一行，不要替他改。"
    "追问里最多出现一个问题，语气像严格的助教，不超过 80 字。"
)


class Adversary:
    def __init__(self, router: Router) -> None:
        self.router = router

    def challenge(
        self,
        item: DefectItem,
        answer: StudentAnswer,
        round_index: int,
        *,
        budget: CallBudget,
        view: Optional[SealedView] = None,
        templates: Sequence[str] = (),
        on_token=None,
    ) -> str:
        evidence_lines = []
        if view is not None:
            for evidence_id in item.evidence_ids:
                try:
                    span = view.fetch(evidence_id)
                except Exception:  # 证据缺失不该让这一轮塌掉
                    continue
                evidence_lines.append("[%s] %s" % (span.evidence_id, span.quote[:200]))

        prompt = [
            "TASK=adversary",
            "ROUND=%d" % round_index,
            "item_id=%s" % item.item_id,
            "缺陷类型=%s" % item.defect_type.value,
            "本轮学生回答：",
            answer.text,
            "他引用的证据：%s" % (", ".join(answer.cited_evidence_ids) or "无"),
            "他给的修复：%s" % (answer.proposed_fix or "无"),
        ]
        if templates:
            prompt.append("可参考的追问角度（不要照抄）：")
            prompt.extend("- " + t for t in templates)
        if evidence_lines:
            prompt.append("已封存的证据（只读，不要重新检索）：")
            prompt.extend(evidence_lines)

        response = self.router.call(
            "adversary",
            [system(_SYSTEM), user("\n".join(prompt))],
            budget=budget,
            temperature=0.5,
            on_token=on_token,
        )
        return response.text.strip()
