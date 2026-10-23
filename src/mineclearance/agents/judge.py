"""两级裁判。

切分点不是价格，是可判性：
    决策档只吃一张由代码抽出来的结构化表（有没有定位、有没有触发条件、
    有没有修复、引了哪几段），回一个封闭集标签加一个置信度。
    它不读学生的原话——模型对「没有缺陷」的判断天然偏，读到原话就被带跑。
    置信度低或只判到「部分」时，才升级到推理档，去读原文与整段对话。
    升级每次会话最多 1 次，所以总次数封在 12 以内。

引用核验不花调用：拿学生标的 evidence_id 与封存证据比对，纯本地算。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

from ..config import Settings
from ..llm import Router, system, user
from ..budget import BudgetExceeded, CallBudget
from ..rag import SealedView
from ..schemas import (
    CitationReport,
    DefectItem,
    JudgeLabel,
    Level,
    StudentAnswer,
    Verdict,
)

# 注意：示例里的 JSON 花括号写成 {{ }}，因为阈值要经 .format() 注入。
_JUDGE_SYSTEM = (
    "你是判级员。输入是一张抽取表，不是学生的原话。"
    "只输出 JSON：{{\"items\": [{{\"item_id\": ..., \"label\": \"defect_present|no_defect\", "
    "\"confidence\": 0-1 的小数, \"note\": \"一句话\"}}]}}。"
    "标签只有命中与未命中两个取值，没有「部分正确」；拿不准就写低置信度，"
    "不要发明第三个标签。定位或触发条件缺一栏，就不要给 defect_present。"
    "置信度低于 {threshold:.2f} 就如实写低，不要凑整。"
)

_ESCALATE_SYSTEM = (
    "你是复核判级员。现在允许你读原文与整段对话。"
    "只输出 JSON：{\"label\": ..., "
    "\"level\": \"L0_false_alarm|L1_perception|L2_localization|L3_attribution|L4_repair\", "
    "\"rationale\": \"两句话，说明为什么是这个等级\"}。"
    "L0 只用于误报：学生指认之处经证据核实并无该缺陷，或张冠李戴、"
    "把无关写法当雷。等级只能从闭集里选，不要发明新标签。"
)

_LINE_RE = re.compile(r"(第\s*\d+\s*行|line\s*\d+|L\d+:\d+)", re.IGNORECASE)
_IDENT_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]{3,}")
_TRIGGER_WORDS = ("触发", "当", "如果", "输入", "边界", "空", "越界", "when", "input", "empty", "null")
_FIX_WORDS = ("改成", "应改为", "应该", "替换", "修复", "改为", "fix", "replace", "should")


def extract_row(item: DefectItem, rounds: Sequence) -> Dict[str, object]:
    """抽取表的一行。这里是代码在写表，不是模型在写表——单写者。"""
    answer: StudentAnswer = rounds[-1].answer if rounds else StudentAnswer(text="（未作答）")
    text = answer.text
    identifiers = {m.group(1) for m in re.finditer(r"([A-Za-z_][A-Za-z0-9_]{3,})", item.original)}
    location_hit = bool(_LINE_RE.search(text)) or any(ident in text for ident in identifiers)
    trigger_hit = any(word in text.lower() for word in _TRIGGER_WORDS)
    fix_hit = any(word in text.lower() for word in _FIX_WORDS) or bool(answer.proposed_fix.strip())

    # 闭表只能判「停在哪一档」，判不了「说的是不是真的」：
    # 误报（L0）要对照原文与证据辨方向，只有读原文的升级层能给，表从 L1 起步。
    if not location_hit:
        derived = Level.L1
    elif not trigger_hit:
        derived = Level.L2
    elif not fix_hit:
        derived = Level.L3
    else:
        derived = Level.L4

    return {
        "item_id": item.item_id,
        "defect_type": item.defect_type.value,
        "rounds": len(rounds),
        "location_hit": location_hit,
        "trigger_hit": trigger_hit,
        "fix_hit": fix_hit,
        "cited": list(answer.cited_evidence_ids),
        "derived_level": derived.value,
    }


def citation_report(cited: Sequence[str], sealed_ids: Sequence[str]) -> CitationReport:
    sealed = list(dict.fromkeys(sealed_ids))
    cited_clean = list(dict.fromkeys(c for c in cited if c))
    supported = tuple(c for c in cited_clean if c in sealed)
    unsupported = tuple(c for c in cited_clean if c not in sealed)
    missing = tuple(s for s in sealed if s not in cited_clean)
    precision = len(supported) / len(cited_clean) if cited_clean else 0.0
    recall = len(supported) / len(sealed) if sealed else 0.0
    return CitationReport(
        precision=round(precision, 4),
        recall=round(recall, 4),
        supported=supported,
        unsupported=unsupported,
        missing=missing,
    )


@dataclass(frozen=True)
class Decision:
    item_id: str
    label: JudgeLabel
    confidence: float
    note: str = ""


class Judge:
    def __init__(self, router: Router, settings: Settings) -> None:
        self.router = router
        self.settings = settings
        self.escalations = 0

    def settle(
        self,
        runs: Sequence,
        *,
        budget: CallBudget,
        view: Optional[SealedView] = None,
    ) -> List[Verdict]:
        if not runs:
            return []
        rows = [extract_row(run.item, run.rounds) for run in runs]
        decisions = self._decide(rows, budget)

        escalate_id = self._pick_escalation(decisions)
        escalated_payload: Optional[dict] = None
        if escalate_id is not None:
            escalated_payload = self._escalate(escalate_id, runs, rows, budget, view)

        verdicts: List[Verdict] = []
        for run, row in zip(runs, rows):
            decision = decisions.get(str(row["item_id"]))
            level = Level(str(row["derived_level"]))
            escalated = escalated_payload is not None and escalated_payload.get("item_id") == row["item_id"]
            if decision is None:
                # 预算不足或模型输出越域被丢弃时，退回本地抽取表直判。
                # 闭集只有命中/未命中：学生至少指出了位置或触发条件就算命中，
                # 不发明「部分正确」这种中间态（闸二）。
                hit = bool(row["location_hit"] or row["trigger_hit"])
                decision = Decision(
                    str(row["item_id"]),
                    JudgeLabel.DEFECT if hit else JudgeLabel.NONE,
                    0.5,
                    "预算不足或模型输出越域，按抽取表直判",
                )
            if escalated:
                level = Level(escalated_payload.get("level") or level.value)
            answer = run.rounds[-1].answer if run.rounds else StudentAnswer(text="（未作答）")
            verdicts.append(
                Verdict(
                    item_id=run.item.item_id,
                    label=decision.label,
                    level=level,
                    confidence=decision.confidence,
                    escalated=escalated,
                    rationale=decision.note if not escalated else str(escalated_payload.get("rationale", "")),
                    citation=citation_report(answer.cited_evidence_ids, run.item.evidence_ids),
                )
            )
        return verdicts

    # ---- 决策档 ----

    def _decide(self, rows: Sequence[Dict[str, object]], budget: CallBudget) -> Dict[str, Decision]:
        system_prompt = _JUDGE_SYSTEM.format(threshold=self.settings.escalate_confidence)
        lines = ["TASK=judge_decision", "抽取表（由系统生成，不含学生原文）："]
        lines.append(json.dumps(list(rows), ensure_ascii=False, indent=2))
        for row in rows:
            lines.append("item_id=%s" % row["item_id"])
        try:
            response = self.router.call(
                "judge_decision",
                [system(system_prompt), user("\n".join(lines))],
                budget=budget,
                temperature=0.0,
            )
        except BudgetExceeded:
            return {}
        return _parse_decisions(response.text)

    # ---- 升级 ----

    def _pick_escalation(self, decisions: Dict[str, Decision]) -> Optional[str]:
        """升级给最没把握的那一个。触发条件只有置信度，不看标签。

        标签是闭集（命中/未命中），没有可比的中间态；拿不准程度全部由置信度表达，
        所以挑最低置信度就是挑最该复核的。
        """
        if not decisions:
            return None
        worst = min(decisions.values(), key=lambda d: d.confidence)
        return worst.item_id if worst.confidence < self.settings.escalate_confidence else None

    def _escalate(
        self,
        item_id: str,
        runs: Sequence,
        rows: Sequence[Dict[str, object]],
        budget: CallBudget,
        view: Optional[SealedView],
    ) -> Optional[dict]:
        run = next((r for r in runs if r.item.item_id == item_id), None)
        if run is None:
            return None
        row = next((r for r in rows if r["item_id"] == item_id), None)
        evidence = []
        if view is not None:
            for evidence_id in run.item.evidence_ids[: self.settings.rag_judge_top_k]:
                try:
                    span = view.fetch(evidence_id)
                except Exception:
                    continue
                evidence.append("[%s] %s" % (span.evidence_id, span.quote[:400]))

        dialogue = []
        for record in run.rounds:
            dialogue.append("学生（第 %d 轮）：%s" % (record.index, record.answer.text))
            if record.challenge:
                dialogue.append("质询：%s" % record.challenge)

        messages = [
            system(_ESCALATE_SYSTEM),
            user(
                "\n".join(
                    [
                        "TASK=judge_escalation",
                        "item_id=%s" % item_id,
                        "缺陷类型=%s" % run.item.defect_type.value,
                        "期望等级=%s" % run.item.expected_level.value,
                        "抽取表：%s" % json.dumps(row, ensure_ascii=False),
                        "埋雷版材料：",
                        run.item.planted,
                        "已封存证据：",
                        "\n".join(evidence) or "（无）",
                        "对话：",
                        "\n".join(dialogue),
                    ]
                )
            ),
        ]
        try:
            response = self.router.call(
                "judge_escalation", messages, budget=budget, temperature=0.0
            )
        except BudgetExceeded:
            return None
        self.escalations += 1
        payload = _parse_object(response.text)
        if not payload:
            return None
        payload["item_id"] = item_id
        return payload


def _parse_object(text: str) -> dict:
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        return {}
    try:
        payload = json.loads(text[start : end + 1])
    except ValueError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _parse_decisions(text: str) -> Dict[str, Decision]:
    """解析决策层返回。

    越域的条目直接丢弃，不降级也不补救：槽位有值域是闸三的最后一环，
    把非法标签翻译成「接近的合法标签」等于给模型的越权开口子。
    丢掉的条目由 Judge.settle 退回本地抽取表直判，那条路不需要模型。
    """
    payload = _parse_object(text)
    decisions: Dict[str, Decision] = {}
    for entry in payload.get("items", []):
        if not isinstance(entry, dict):
            continue
        item_id = str(entry.get("item_id", "")).strip()
        if not item_id:
            continue
        try:
            label = JudgeLabel(str(entry.get("label", "")).strip())
        except ValueError:
            continue
        try:
            confidence = float(entry.get("confidence", 0.0))
        except (TypeError, ValueError):
            confidence = 0.0
        decisions[item_id] = Decision(
            item_id=item_id,
            label=label,
            confidence=min(1.0, max(0.0, confidence)),
            note=str(entry.get("note", "")),
        )
    return decisions
