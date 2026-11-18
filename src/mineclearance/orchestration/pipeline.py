"""主链：一条确定性的线，只有一个环。

离线（0 次在线）：取题或命中题库 → 埋雷 → 探针复核 → 预取证据 → 封印
在线（≤12 次）：逐题对抗 2–3 轮 → 结算 1 次（必要时升级 1 次）→ 复盘 1 次

拆成 open / submit / settle 三段，是为了同时服务两种用法：
    Web 端：一场会话跨多个请求，学生一轮一轮交；
    评测与单测：run() 用脚本作答一口气跑完，逐字段断言调用次数。
两套走的是同一段代码，不存在「演示版」和「评测版」两套逻辑。
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field, replace
from typing import Dict, List, Optional, Protocol, Sequence

from ..agents import Adversary, Builder, Judge, Planter, Reporter
from ..agents.probe import Probe
from ..config import Settings
from ..llm import Router
from ..rag import Retriever, SealedView, as_query, rank_and_cut
from ..schemas import (
    DefectItem,
    ItemRun,
    ItemSpec,
    Level,
    RoundRecord,
    SessionReport,
    StudentAnswer,
)
from ..budget import BudgetExceeded, CallBudget
from .cache import QuestionBank, StructuralMemory

# 留给结算与复盘。对抗打到这里就停手，保证 12 次的硬上限不是靠「运气好」守住的。
RESERVE_CALLS = 3
PREPARED_SOURCE = 3  # 一道题封存几段证据（召回 8–12，进裁判只留 3）
DEFECT_RAG_CODES = {
    "logic": "R06",
    "boundary": "R02",
    "api_misuse": "R01",
    "data_leak": "R07",
    "type_confusion": "R05",
    "security": "R08",
    "perf": "R03",
    "doc_mismatch": "R06",
}


class AnswerProvider(Protocol):
    """学生作答来源。Web 端接表单，评测时接脚本，测试里接固定脚本。"""

    def submit(self, item: DefectItem, round_index: int, challenge: str) -> StudentAnswer: ...


@dataclass(frozen=True)
class Preparation:
    item: DefectItem
    accepted: bool
    reason: str
    bank_hit: bool


@dataclass
class Handle:
    """一场进行中的会话。只在这一层持有可变状态，其余全是冻结对象。"""

    session_id: str
    budget: CallBudget
    runs: List[ItemRun] = field(default_factory=list)
    rejected: int = 0
    started: float = field(default_factory=time.time)
    settled: bool = False


class Session:
    def __init__(
        self,
        *,
        settings: Settings,
        router: Router,
        retriever: Retriever,
        answers: Optional[AnswerProvider] = None,
        bank: Optional[QuestionBank] = None,
        memory: Optional[StructuralMemory] = None,
        probe: Optional[Probe] = None,
    ) -> None:
        self.settings = settings
        self.router = router
        self.retriever = retriever
        self.answers = answers
        self.bank = bank if bank is not None else QuestionBank()
        self.memory = memory if memory is not None else StructuralMemory()
        self.builder = Builder(router)
        self.planter = Planter(router, probe)
        self.adversary = Adversary(router)
        self.judge = Judge(router, settings)
        self.reporter = Reporter(router)
        self.trace: List[str] = []

    # ---- 一段：离线准备 ----

    def open(self, specs: Sequence[ItemSpec], session_id: Optional[str] = None) -> Handle:
        handle = Handle(
            session_id=session_id or ("s_" + uuid.uuid4().hex[:10]),
            budget=CallBudget(
                cap=self.settings.max_calls_per_session,
                cost_cap_cny=self.settings.cost_budget_cny,
            ),
        )
        self._log("会话 %s 开始，%d 张出题单，硬上限 %d 次" % (handle.session_id, len(specs), handle.budget.cap))

        preparations = self._prepare(specs)
        self._seal()

        accepted = [p for p in preparations if p.accepted]
        # 分母用出题单总数而不是 preparations：召回为空的题连 Preparation 都不生成，
        # 用 preparations 会把它静默漏掉，账面比实际少。
        handle.rejected = len(specs) - len(accepted)
        if handle.rejected:
            self._log("剔除 %d 道未通过复核的题（不进本场评分）" % handle.rejected)

        for preparation in accepted:
            handle.runs.append(
                ItemRun(item=preparation.item, target_rounds=self._target_rounds(preparation.item))
            )
        return handle

    # ---- 二段：逐轮对抗 ----

    def submit(
        self,
        handle: Handle,
        item_id: str,
        answer: StudentAnswer,
        *,
        on_token=None,
    ) -> Optional[RoundRecord]:
        run = self._run_of(handle, item_id)
        if run is None:
            raise KeyError("这场会话里没有这道题: %s" % item_id)
        if len(run.rounds) >= run.target_rounds:
            self._log("%s 已达目标轮次 %d，不再追问" % (item_id, run.target_rounds))
            return None
        if handle.budget.remaining <= RESERVE_CALLS:
            self._log("%s 提前收束：余量 %d 次，留给结算与复盘" % (item_id, handle.budget.remaining))
            return None

        index = len(run.rounds) + 1
        previous = run.rounds[-1].challenge if run.rounds else ""
        try:
            challenge = self.adversary.challenge(
                run.item,
                answer,
                index,
                budget=handle.budget,
                view=SealedView(self.retriever),
                templates=self.memory.templates_for(run.item.defect_type, run.item.expected_level),
                on_token=on_token,
            )
        except BudgetExceeded as exc:
            self._log("预算拒绝了一次对抗调用：%s" % exc)
            return None

        record = RoundRecord(index=index, answer=answer, challenge=challenge, calls=1)
        handle.runs[handle.runs.index(run)] = run.append(record)
        if previous and index > 1:
            self._log("%s 第 %d 轮质询已发出" % (item_id, index))
        return record

    # ---- 三段：结算 ----

    def settle(self, handle: Handle) -> SessionReport:
        if handle.settled:
            raise RuntimeError("这场会话已经结算过了: %s" % handle.session_id)
        verdicts = tuple(
            self.judge.settle(handle.runs, budget=handle.budget, view=SealedView(self.retriever))
        )
        self._log("结算完成：%d 道题，升级 %d 次" % (len(verdicts), self.judge.escalations))

        rounds_by_item: Dict[str, int] = {run.item.item_id: len(run.rounds) for run in handle.runs}
        markdown = self.reporter.write(
            handle.session_id, verdicts, rounds_by_item=rounds_by_item, budget=handle.budget
        )
        rag_usage = self._rag_usage(handle.runs)
        markdown = self._append_rag_summary(markdown, rag_usage)
        self._log(
            "RAG 使用概览：主判例绑定 %d 条，缺陷模式 %d 条，正确反例 %d 条；实际参考字符 %d"
            % (
                rag_usage["contribution"]["case_references_bound"],
                rag_usage["contribution"]["pattern_references_bound"],
                rag_usage["contribution"]["negative_references_bound"],
                rag_usage["agent_reference_chars"],
            )
        )
        handle.settled = True

        report = SessionReport(
            session_id=handle.session_id,
            verdicts=verdicts,
            calls=handle.budget.total,
            cost_cny=handle.budget.cost_cny,
            latency_ms=handle.budget.latency_ms or int((time.time() - handle.started) * 1000),
            unverified_items=handle.rejected,
            markdown=markdown,
            stage_calls=handle.budget.stage_calls(),
            rag_usage=rag_usage,
        )
        self._log(
            "会话结束：调用 %d/%d 次，成本 %.4f 元，阶段分布 %s"
            % (report.calls, handle.budget.cap, report.cost_cny, report.stage_calls)
        )
        return report

    # ---- 批量：评测与冒烟 ----

    def run(self, specs: Sequence[ItemSpec], session_id: Optional[str] = None) -> SessionReport:
        if self.answers is None:
            raise RuntimeError("批量 run() 需要构造时传入 answers")
        handle = self.open(specs, session_id)
        for item_id in [run.item.item_id for run in handle.runs]:
            challenge = ""
            while True:
                current = self._run_of(handle, item_id)
                if current is None or len(current.rounds) >= current.target_rounds:
                    break
                answer = self.answers.submit(current.item, len(current.rounds) + 1, challenge)
                record = self.submit(handle, item_id, answer)
                if record is None:
                    break
                challenge = record.challenge
            finished = self._run_of(handle, item_id)
            self._log("%s 完成 %d 轮对抗" % (item_id, len(finished.rounds) if finished else 0))
        return self.settle(handle)

    @staticmethod
    def _run_of(handle: Handle, item_id: str) -> Optional[ItemRun]:
        return next((r for r in handle.runs if r.item.item_id == item_id), None)

    # ---- 离线内部：取题、埋雷、复核、预取 ----

    def _prepare(self, specs: Sequence[ItemSpec]) -> List[Preparation]:
        preparations: List[Preparation] = []
        for spec in specs:
            key = spec.fingerprint()
            cached = self.bank.get(key)
            if cached is not None:
                self._log("题库命中 %s，跳过出题与埋雷" % spec.item_id)
                item = self._with_cases(self._rebind_evidence(cached))
                preparations.append(
                    Preparation(item=item, accepted=item.verified, reason="题库复用", bank_hit=True)
                )
                continue

            original = self.builder.draft(spec)
            doc_id = "doc_%s" % spec.item_id
            self.retriever.index(doc_id, original, language=spec.language)
            chunks = self.retriever.retrieve(
                as_query(spec.topic, spec.defect_type.value, spec.language),
                top_k=self.settings.rag_top_k,
                doc_id=doc_id,
            )
            evidence_ids = [c.evidence_id for c in rank_and_cut(chunks, PREPARED_SOURCE)]
            if not evidence_ids:
                self._log("出题单 %s 召回为空，无法建证据链" % spec.item_id)
                continue

            outcome = self.planter.plant(spec, original, evidence_ids, tests=self.builder.contracts.get(spec.item_id, ""))
            self._log("%s 独立测试：原版=%s；埋雷版=%s" % (
                spec.item_id, outcome.original_probe, outcome.planted_probe))
            self._log(
                "埋雷 %s：%s（%s）"
                % (spec.item_id, "通过" if outcome.accepted else "剔除", outcome.reason)
            )
            if outcome.accepted:
                prepared_item = self._with_cases(outcome.item)
                self.bank.put(prepared_item, key=key)
            else:
                prepared_item = outcome.item
            preparations.append(
                Preparation(
                    item=prepared_item,
                    accepted=outcome.accepted,
                    reason=outcome.reason,
                    bank_hit=False,
                )
            )
        return preparations

    def _with_cases(self, item: DefectItem) -> DefectItem:
        prepare = getattr(self.retriever, "prepare_cases", None)
        if not callable(prepare):
            return item
        primary_query = as_query(item.title, item.defect_type.value, item.language)
        defect_query = as_query(
            item.diff,
            item.defect_type.value,
            item.language,
            context=item.rubric_hint,
        )
        try:
            case_ids = prepare(primary_query, alternate_queries=(defect_query,))
        except TypeError:
            # 兼容只实现旧 prepare_cases(query) 的本地/第三方检索器。
            case_ids = prepare(primary_query)
        self._log("%s 封存 %d 条真实判例参考" % (item.item_id, len(case_ids)))
        auxiliary = getattr(self.retriever, "prepare_auxiliary", None)
        if not callable(auxiliary):
            return replace(item, case_evidence_ids=case_ids)
        references = auxiliary(
            " ".join((primary_query, defect_query)),
            expected_code=DEFECT_RAG_CODES.get(item.defect_type.value, ""),
        )
        pattern_ids = tuple(references.get("patterns", ()))
        negative_ids = tuple(references.get("negative_code", ()))
        self._log("%s 辅助参考：缺陷模式=%d，正确反例=%d" % (
            item.item_id, len(pattern_ids), len(negative_ids)))
        return replace(
            item,
            case_evidence_ids=case_ids,
            pattern_evidence_ids=pattern_ids,
            negative_evidence_ids=negative_ids,
        )

    def _rebind_evidence(self, item: DefectItem) -> DefectItem:
        """题库里的题带着旧 id。重新索引一遍原文，把证据链重新绑到本次索引上。"""
        doc_id = "doc_%s" % item.item_id
        self.retriever.index(doc_id, item.original, language=item.language)
        alive: List[str] = []
        for evidence_id in item.evidence_ids:
            try:
                self.retriever.fetch(evidence_id)
                alive.append(evidence_id)
            except Exception:
                continue
        if len(alive) == len(item.evidence_ids):
            return item
        chunks = self.retriever.retrieve(
            as_query(item.title, item.defect_type.value, item.language),
            top_k=self.settings.rag_top_k,
            doc_id=doc_id,
        )
        rebound = [c.evidence_id for c in rank_and_cut(chunks, PREPARED_SOURCE)]
        self._log("题库题 %s 的证据 id 失效，重新绑定 %d 段" % (item.item_id, len(rebound)))
        return replace(item, evidence_ids=tuple(rebound or item.evidence_ids))

    def _seal(self) -> None:
        self.retriever.seal()
        self._log("索引已封印：之后只允许按 evidence_id 取回")

    def _target_rounds(self, item: DefectItem) -> int:
        remembered = self.memory.rounds_for(item.defect_type, item.expected_level)
        if remembered is not None:
            self._log("结构记忆给出 %s 的轮次=%d（0 次调用）" % (item.item_id, remembered))
            base = remembered
        else:
            base = 2 if item.expected_level.rank <= Level.L2.rank else 3
        return max(self.settings.min_rounds, min(self.settings.max_rounds, base))

    def _rag_usage(self, runs: Sequence[ItemRun]) -> dict:
        """只输出 RAG 参与度统计，不把共享判例正文或证据编号暴露到报告。"""
        summary_fn = getattr(self.retriever, "summary", None)
        raw_summary = summary_fn() if callable(summary_fn) else {}
        if not isinstance(raw_summary, dict):
            raw_summary = {}
        items = []
        case_bound = pattern_bound = negative_bound = 0
        items_with_cases = items_with_auxiliary = 0
        for run in runs:
            case_count = len(tuple(run.item.case_evidence_ids))
            pattern_count = len(tuple(getattr(run.item, "pattern_evidence_ids", ())))
            negative_count = len(tuple(getattr(run.item, "negative_evidence_ids", ())))
            case_bound += case_count
            pattern_bound += pattern_count
            negative_bound += negative_count
            if case_count:
                items_with_cases += 1
            if pattern_count or negative_count:
                items_with_auxiliary += 1
            items.append({
                "item_id": run.item.item_id,
                "case_references": case_count,
                "pattern_references": pattern_count,
                "negative_references": negative_count,
                "has_rag_support": bool(case_count or pattern_count or negative_count),
            })
        retrieval_stats = raw_summary.get("retrieval_stats", {})
        quality_stats = raw_summary.get("quality_stats", {})
        return {
            "backend": raw_summary.get("backend", type(self.retriever).__name__),
            "connected": raw_summary.get("connected"),
            "degraded": raw_summary.get("degraded", False),
            "retrieval_requests": raw_summary.get("retrieval_requests", 0),
            "case_query_count": raw_summary.get("case_query_count", 0),
            "retrieval_stats": retrieval_stats if isinstance(retrieval_stats, dict) else {},
            "quality_stats": quality_stats if isinstance(quality_stats, dict) else {},
            "agent_reference_chars": int(quality_stats.get("agent_reference_chars", 0) or 0)
            if isinstance(quality_stats, dict) else 0,
            "contribution": {
                "case_references_bound": case_bound,
                "pattern_references_bound": pattern_bound,
                "negative_references_bound": negative_bound,
                "items_with_cases": items_with_cases,
                "items_with_auxiliary": items_with_auxiliary,
                "items_total": len(items),
            },
            "items": items,
        }

    @staticmethod
    def _append_rag_summary(markdown: str, rag_usage: dict) -> str:
        contribution = rag_usage["contribution"]
        return (
            markdown.rstrip()
            + "\n\n## RAG 使用概览\n\n"
            + "- 后端：%s；检索请求：%d；最终绑定主判例：%d 条。\n"
            % (rag_usage["backend"], rag_usage["retrieval_requests"], contribution["case_references_bound"])
            + "- 缺陷模式：%d 条；正确反例：%d 条；实际送入 Agent 的参考字符：%d。\n"
            % (
                contribution["pattern_references_bound"],
                contribution["negative_references_bound"],
                rag_usage["agent_reference_chars"],
            )
            + "- 这部分只作为审查口径参考，不替代本题代码证据。"
        )

    def _log(self, message: str) -> None:
        self.trace.append(message)


def summarize_trace(report: SessionReport, trace: Sequence[str] = ()) -> str:
    lines = list(trace)
    lines.append("")
    lines.append(
        "调用 %d 次；成本 %.4f 元；阶段 %s" % (report.calls, report.cost_cny, report.stage_calls)
    )
    for verdict in report.verdicts:
        lines.append(
            "  %s  %s  %s  置信度 %.2f  引用 %d/%d"
            % (
                verdict.item_id,
                verdict.label.value,
                verdict.level.value,
                verdict.confidence,
                len(verdict.citation.supported),
                len(verdict.citation.supported) + len(verdict.citation.missing),
            )
        )
    if report.unverified_items:
        lines.append("  未通过复核、未参与评分：%d 道" % report.unverified_items)
    return "\n".join(lines)
