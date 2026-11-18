"""报告：把结算结果写成学生看得懂的一段话。

只花 1 次调用，且失败不影响会话——预算耗尽或者网关超时，就退回本地模板。
学生拿不到「模型写的漂亮总结」可以接受，拿不到「这次判了几级」不行。
"""

from __future__ import annotations

from typing import Sequence

from ..llm import Router, system, user
from ..budget import CallBudget
from ..schemas import Verdict

_SYSTEM = (
    "你是复盘教练。根据结算表写一段复盘，300 字以内。"
    "结构：这次你最该补的一处能力、一处你已经做对的地方、下一步练什么。"
    "不要复述分数，不要编造没发生的事。"
)


class Reporter:
    def __init__(self, router: Router) -> None:
        self.router = router
        self.fallback_used = False

    def write(
        self,
        session_id: str,
        verdicts: Sequence[Verdict],
        *,
        rounds_by_item: dict,
        budget: CallBudget,
    ) -> str:
        if not verdicts:
            self.fallback_used = True
            # 一道可判的题都没有时，让模型写一段「本次无可判题」是纯浪费，
            # 而且这段话是确定的，本地模板说得更准。不花这 1 次调用。
            return _local_report(verdicts)

        table = [
            "TASK=report",
            "session_id=%s" % session_id,
            "结算表：",
        ]
        for verdict in verdicts:
            table.append(
                "- %s | 标签=%s | 等级=%s | 置信度=%.2f | 轮次=%s | 引用命中=%d/%d"
                % (
                    verdict.item_id,
                    verdict.label.value,
                    verdict.level.value,
                    verdict.confidence,
                    rounds_by_item.get(verdict.item_id, 0),
                    len(verdict.citation.supported),
                    len(verdict.citation.supported) + len(verdict.citation.missing),
                )
            )
        try:
            response = self.router.call(
                "report",
                [system(_SYSTEM), user("\n".join(table))],
                budget=budget,
                temperature=0.4,
            )
            text = response.text.strip()
            if text:
                return text
        except Exception:  # 预算耗尽、网关挂了，都不该让会话失败
            pass
        self.fallback_used = True
        return _local_report(verdicts)


def _local_report(verdicts: Sequence[Verdict]) -> str:
    if not verdicts:
        return "## 本次没有可判的题\n\n所有题目都在埋雷复核阶段被剔除，请检查出题环节。"
    lines = ["## 本次排雷记录", ""]
    for verdict in verdicts:
        lines.append(
            "- %s：%s（%s，置信度 %.2f%s）"
            % (
                verdict.item_id,
                verdict.label.value,
                verdict.level.value,
                verdict.confidence,
                "，已升级复核" if verdict.escalated else "",
            )
        )
    unsupported = sum(len(v.citation.unsupported) for v in verdicts)
    if unsupported:
        lines.append("")
        lines.append("有 %d 处引用不在封存证据里，这类「凭印象指认」是最常见的扣分点。" % unsupported)
    return "\n".join(lines)
