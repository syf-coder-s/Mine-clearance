"""Web 端会话状态机。只依赖标准库，FastAPI 只是外面一层薄壳。

为什么把状态机拆出来：
    单测不该为了测「结算两次要拒」去装 fastapi。tests/test_api_store.py 直接驱动这里，
    HTTP 层就只剩 JSON 进、JSON 出，出错概率和需要测试的面积都小一个数量级。

三个不能让步的规矩，都落在这一层：
    1  发给学生的题**不带** original / diff / rubric_hint / expected_level。
       前端拿到 original 就等于拿到答案，这是最省事也最致命的泄漏。
    2  证据片段只在「这行字在埋雷版里也出现」时才回显。
       否则等于把原版正确代码摆出来给学生抄。
    3  结算之后 submit 一律拒。会话是单向的，允许补交就会有人反复试探判级口径。
"""

from __future__ import annotations

import difflib
import os
import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Sequence

from ..agents import MarkerProbe, Probe, PYTEST_PROBE
from ..agents.pure_probe import PurePythonProbe
from ..config import DEFAULT_SETTINGS, Settings
from ..llm import Router, build_router
from ..orchestration import QuestionBank, Session
from ..orchestration.pipeline import RESERVE_CALLS
from ..rag import IndexSealed, RAGError, Retriever, build_retriever
from ..schemas import (
    SCHEMA_VERSION,
    DefectType,
    ItemRun,
    ItemSpec,
    Level,
    StudentAnswer,
    to_dict,
)

DEFAULT_TTL_S = 1800.0  # 一场训练 15 分钟，半小时不动就回收

# 出题单不带 query：query 由 rag.as_query() 拼一次就定稿，不做在线改写。
DEFAULT_SPECS: tuple = (
    ("在有序数组里找最接近目标值的元素", DefectType.BOUNDARY, Level.L2),
    ("等距候选时的返回值稳定性", DefectType.LOGIC, Level.L3),
    ("边界比较运算符的修复", DefectType.BOUNDARY, Level.L4),
    ("分页接口的越界处理", DefectType.API_MISUSE, Level.L3),
    ("日志里打印用户手机号的那一行", DefectType.DATA_LEAK, Level.L2),
)


class StoreError(Exception):
    """带 HTTP 语义的领域错误。main.py 只按 status 翻译，不猜。"""

    status = 400


class SessionNotFound(StoreError):
    status = 404


class UnknownItem(StoreError):
    status = 404


class SessionClosed(StoreError):
    status = 409


class Sealed(StoreError):
    status = 409


class UpstreamError(StoreError):
    status = 502


class EvidenceForbidden(StoreError):
    status = 403


class CitationOutsideAnchor(StoreError):
    status = 422


@dataclass
class _Entry:
    session_id: str
    session: Session
    handle: object
    retriever: Retriever
    router: Router
    created: float
    touched: float
    lock: threading.RLock = field(default_factory=threading.RLock)


def map_span_to_planted(original: str, planted: str, char_start: int, char_end: int) -> tuple:
    """把 original 里的字符区间映射到 planted 的行区间。

    证据 span 的 char_start/char_end 是**原版代码**里的字符偏移，而发给学生的
    是埋雷版：埋雷会把行改坏、还可能多出几行，原版偏移直接切埋雷版必然错位。
    这里先按换行求原版 0-based 行号（闭区间），再用 SequenceMatcher 建
    「原版行号 → 埋雷版行号」映射，最后从埋雷版里取对应行的文本当 excerpt。
    任何一步对不上都退化为 (0, 0, "")——绝不拿原版的行给学生看。

    行号为 1-based、闭区间；映射失败返回 (0, 0, "")。
    """
    try:
        if not original or not planted:
            return (0, 0, "")
        if char_start < 0 or char_end < char_start or char_start >= len(original):
            return (0, 0, "")
        orig_lines = original.splitlines()
        plant_lines = planted.splitlines()
        if not orig_lines or not plant_lines:
            return (0, 0, "")

        start0 = original.count("\n", 0, char_start)
        end0 = original.count("\n", 0, max(char_start, min(char_end, len(original)) - 1))
        start0 = min(start0, len(orig_lines) - 1)
        end0 = min(max(end0, start0), len(orig_lines) - 1)

        mapping: Dict[int, int] = {}
        sm = difflib.SequenceMatcher(None, orig_lines, plant_lines, autojunk=False)
        for tag, i1, i2, j1, j2 in sm.get_opcodes():
            if tag == "equal":
                for k in range(i1, i2):
                    mapping[k] = j1 + (k - i1)
            elif tag in ("replace", "delete"):
                dest = min(j1, len(plant_lines) - 1)
                for k in range(i1, i2):
                    mapping[k] = dest
            # insert：原版里没有对应行，跳过

        p_start = mapping.get(start0)
        p_end = mapping.get(end0)
        if p_start is None or p_end is None:
            return (0, 0, "")
        p_start = min(max(p_start, 0), len(plant_lines) - 1)
        p_end = min(max(p_end, 0), len(plant_lines) - 1)
        if p_start > p_end:
            p_start, p_end = p_end, p_start

        excerpt = "\n".join(plant_lines[p_start : p_end + 1])
        if not excerpt.strip():
            return (0, 0, "")
        return (p_start + 1, p_end + 1, excerpt)
    except Exception:
        return (0, 0, "")


def build_probe(settings: Settings) -> Optional[Probe]:
    """探针：演练模式用确定性替身，真实模式必须显式打开。

    默认关闭不是偷懒：CommandProbe 会执行模型写出来的代码。要不要在自己的机器上
    执行它，是部署方的决定，不能由一个默认值替他决定。
    但关掉探针的代价是题目全部被剔除（无法证明雷埋上了），所以这里只打印原因，
    由调用方决定要不要装 pytest。
    """
    if settings.use_mock_llm():
        return MarkerProbe()
    if os.getenv("MC_PROBE", "").strip().lower() in {"1", "true", "yes", "on"}:
        return PurePythonProbe()
    return None


class SessionStore:
    """进程内会话表。单机演示够用；多副本部署要换成 Redis，接口不用改。"""

    def __init__(
        self,
        settings: Optional[Settings] = None,
        *,
        probe: Optional[Probe] = None,
        bank: Optional[QuestionBank] = None,
        router_factory: Callable[[Settings], Router] = build_router,
        retriever_factory: Callable[[Settings], Retriever] = build_retriever,
        ttl_s: float = DEFAULT_TTL_S,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.settings = settings or DEFAULT_SETTINGS
        self.probe = build_probe(self.settings) if probe is None else probe
        self.bank = bank if bank is not None else QuestionBank()
        self.router_factory = router_factory
        self.retriever_factory = retriever_factory
        self.ttl_s = ttl_s
        self.clock = clock
        self._entries: Dict[str, _Entry] = {}
        self._lock = threading.Lock()
        self._bank_retriever: Optional[Retriever] = None  # 仅供离线建库的检索代理
        self._router_probe: Optional[Router] = None  # 只为读厂商隔离标记
        self._last_retriever: Optional[Retriever] = None

    # ---- 一：开场 ----

    def open(self, specs: Optional[Sequence[ItemSpec]] = None) -> dict:
        self._sweep()
        chosen = list(specs) if specs else default_specs(self.settings.items_per_session)

        router = self.router_factory(self.settings)
        retriever = self.retriever_factory(self.settings)
        self._last_retriever = retriever
        session = Session(
            settings=self.settings,
            router=router,
            retriever=retriever,
            bank=self.bank,
            probe=self.probe,
        )
        try:
            handle = session.open(chosen)
        except RAGError as exc:
            raise UpstreamError(str(exc)) from exc

        if not handle.runs and not self.settings.use_mock_llm():
            raise UpstreamError("所有候选题均未通过独立行为测试；未创建可评分会话")

        now = self.clock()
        entry = _Entry(
            session_id=handle.session_id,
            session=session,
            handle=handle,
            retriever=retriever,
            router=router,
            created=now,
            touched=now,
        )
        with self._lock:
            self._entries[entry.session_id] = entry
        return self._view(entry)

    # ---- 二：逐轮作答 ----

    def submit(
        self,
        session_id: str,
        item_id: str,
        text: str,
        *,
        cited: Sequence[str] = (),
        proposed_fix: str = "",
        on_token: Optional[Callable[[str], None]] = None,
    ) -> dict:
        entry = self._get(session_id)
        with entry.lock:
            if entry.handle.settled:
                raise SessionClosed("会话 %s 已结算，不能再交作业" % session_id)
            try:
                answer = StudentAnswer(
                    text=text, cited_evidence_ids=tuple(cited), proposed_fix=proposed_fix
                )
            except ValueError as exc:
                raise StoreError(str(exc)) from exc

            run = _find_run(entry.handle, item_id)
            if run is None:
                raise UnknownItem("这场会话里没有这道题: %s" % item_id)
            if self.settings.rag_provider.lower() == "ragflow" and any(
                evidence_id not in run.item.evidence_ids for evidence_id in cited
            ):
                raise CitationOutsideAnchor("引用编号不在本题封存的可引用证据中")
            if len(run.rounds) >= run.target_rounds:
                # 轮次用完不是错误，是这道题结束了。照常回包，让前端渲染「本题已完成」，
                # 不要把正常状态做成 409 —— 前端会把它当失败提示弹出来。
                return self._closed_item(entry, run, "target_reached")

            record = entry.session.submit(entry.handle, item_id, answer, on_token=on_token)
            entry.touched = self.clock()
            current = _find_run(entry.handle, item_id) or run

            if record is None:
                # 只剩一种原因：预算余量只够结算与复盘了。如实告诉学生，不装作答对了。
                return self._closed_item(entry, current, "budget_guard")

            return {
                "item_id": item_id,
                "accepted": True,
                "reason": "ok",
                "round": record.index,
                "challenge": record.challenge,
                "rounds_done": len(current.rounds),
                "target_rounds": current.target_rounds,
                "finished": len(current.rounds) >= current.target_rounds,
                "budget": _budget_view(entry),
            }

    # ---- 三：结算 ----

    def settle(self, session_id: str) -> dict:
        entry = self._get(session_id)
        with entry.lock:
            if entry.handle.settled:
                raise SessionClosed("会话 %s 已经结算过了" % session_id)
            report = entry.session.settle(entry.handle)
            entry.touched = self.clock()

        payload = to_dict(report)
        payload["verdicts"] = [self._verdict(entry, verdict) for verdict in report.verdicts]
        payload["budget"] = entry.handle.budget.summary()
        payload["trace"] = list(entry.session.trace)
        payload["cost_known"] = entry.router.summary()["cost_known"]
        payload["report_fallback"] = entry.session.reporter.fallback_used
        return payload

    # ---- 只读 ----

    def state(self, session_id: str) -> dict:
        entry = self._get(session_id)
        return self._view(entry, with_items=False) | {
            "settled": entry.handle.settled,
            "items": [
                {
                    "item_id": run.item.item_id,
                    "rounds_done": len(run.rounds),
                    "target_rounds": run.target_rounds,
                    "finished": len(run.rounds) >= run.target_rounds,
                }
                for run in entry.handle.runs
            ],
        }

    def close(self, session_id: str) -> None:
        with self._lock:
            if self._entries.pop(session_id, None) is None:
                raise SessionNotFound("没有这场会话: %s" % session_id)

    def count(self) -> int:
        with self._lock:
            return len(self._entries)

    def anchors(self, session_id: str) -> List[dict]:
        """内部用：这道题在 seal 时刻冻结的证据集合，交给裁决层登记。

        只回题号、文档号、本题证据与内部判例编号。**不带** expected_level、rubric、
        original——锚点里有答案侧信息，所以 /v1/anchor/* 在壳层还有一道内部令牌。
        学生可见的 payload 不经过这里（见 _item）。
        """
        entry = self._get(session_id)
        return [
            {
                "item_id": run.item.item_id,
                "doc_id": "doc_%s" % run.item.item_id,
                "evidence_ids": list(run.item.evidence_ids),
                "case_evidence_ids": list(run.item.case_evidence_ids),
            }
            for run in entry.handle.runs
        ]

    # ---- 预留的 RAG 代理 ----
    #
    # 前端**不允许**直连检索后端：那意味着把 RAG_API_KEY 发到浏览器里。
    # 所以这里做两层代理，且两个方向不对称：
    #     读（retrieve / evidence）：可以代理，但走会话时必须已被封印，改不了索引；
    #     写（index）：不代理。索引只在离线准备阶段由主链写，前端能写就等于能改证据链。

    def retrieve(
        self,
        query: str,
        *,
        top_k: int = 5,
        doc_id: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> dict:
        retriever = self._scoped_retriever(session_id)
        try:
            chunks = retriever.retrieve(query, top_k=top_k, doc_id=doc_id)
        except IndexSealed as exc:
            raise Sealed(str(exc)) from exc
        except RAGError as exc:
            raise UpstreamError(str(exc)) from exc
        return {
            "scope": session_id or "bank",
            "sealed": bool(getattr(retriever, "sealed", False)),
            "items": [
                {
                    "evidence_id": chunk.evidence_id,
                    "doc_id": chunk.doc_id,
                    "chunk_id": chunk.chunk_id,
                    "text": chunk.text,
                    "char_start": chunk.char_start,
                    "char_end": chunk.char_end,
                    "score": chunk.score,
                }
                for chunk in chunks
            ],
        }

    def evidence(self, evidence_id: str, *, session_id: Optional[str] = None) -> dict:
        if session_id:
            entry = self._get(session_id)
            allowed = {eid for run in entry.handle.runs for eid in run.item.evidence_ids}
            if evidence_id not in allowed:
                raise EvidenceForbidden("该证据不属于本会话的学生可读范围")
            if not entry.handle.settled:
                raise EvidenceForbidden("结算前不能读取证据原文")
        retriever = self._scoped_retriever(session_id)
        try:
            span = retriever.fetch(evidence_id)
        except RAGError as exc:
            raise UpstreamError(str(exc)) from exc
        return to_dict(span)

    def rag_summary(self) -> dict:
        retriever = self._last_retriever or self._scoped_retriever(None)
        summary = getattr(retriever, "summary", None)
        return summary() if callable(summary) else {"backend": type(retriever).__name__}

    def vendor_isolated(self) -> bool:
        """对抗方与裁判是否真的分属不同厂商。

        惰性构造一个 router 只为读配置——构造 client 不联网、不花调用。
        /v1/health 上有这一项，是因为「你们怎么保证对抗和裁判不同源」一定会被问到，
        答案应该是 health 页上的一行字，而不是一句保证。
        """
        if self._router_probe is None:
            self._router_probe = self.router_factory(self.settings)
        return bool(getattr(self._router_probe, "vendor_isolated", True))

    def model_routes(self) -> dict:
        if self._router_probe is None:
            self._router_probe = self.router_factory(self.settings)
        return self._router_probe.summary()["model_routes"]

    # ---- 内部 ----

    def _get(self, session_id: str) -> _Entry:
        with self._lock:
            entry = self._entries.get(session_id)
        if entry is None:
            raise SessionNotFound("没有这场会话（可能已超时回收）: %s" % session_id)
        return entry

    def _scoped_retriever(self, session_id: Optional[str]) -> Retriever:
        if session_id:
            return self._get(session_id).retriever
        with self._lock:
            if self._bank_retriever is None:
                self._bank_retriever = self.retriever_factory(self.settings)
            return self._bank_retriever

    def _sweep(self) -> None:
        deadline = self.clock() - self.ttl_s
        with self._lock:
            stale = [sid for sid, entry in self._entries.items() if entry.touched < deadline]
            for sid in stale:
                del self._entries[sid]

    def _view(self, entry: _Entry, *, with_items: bool = True) -> dict:
        handle = entry.handle
        payload = {
            "session_id": entry.session_id,
            "schema_version": SCHEMA_VERSION,
            "unverified_items": handle.rejected,
            "budget": _budget_view(entry),
        }
        if with_items:
            payload["items"] = [self._item(entry, run) for run in handle.runs]
        return payload

    def _item(self, entry: _Entry, run: ItemRun) -> dict:
        item = run.item
        return {
            "item_id": item.item_id,
            "language": item.language,
            "title": item.title,
            "code": item.planted,  # 只给埋雷版
            "rounds_done": len(run.rounds),
            "target_rounds": run.target_rounds,
            "evidence": [self._evidence_hint(entry, item, eid) for eid in item.evidence_ids],
        }

    @staticmethod
    def _evidence_hint(entry: _Entry, item, evidence_id: str) -> dict:
        """证据片段：把原版证据区间映射到埋雷版的行，只回显埋雷版行文本。

        埋雷版里对应行丢了（映射失败）就退化成只有编号，不阻断开局，
        也绝不回显原版的任何一行。
        """
        try:
            span = entry.retriever.fetch(evidence_id)
        except Exception:  # 取不回就退化成只有编号，不阻断开局
            return {
                "evidence_id": evidence_id,
                "excerpt": "",
                "visible_in_code": False,
                "line_start": 0,
                "line_end": 0,
            }
        line_start, line_end, excerpt = map_span_to_planted(
            item.original, item.planted, span.char_start, span.char_end
        )
        return {
            "evidence_id": evidence_id,
            "excerpt": excerpt,
            "visible_in_code": bool(excerpt),
            "line_start": line_start,
            "line_end": line_end,
        }

    @staticmethod
    def _closed_item(entry: _Entry, run: ItemRun, reason: str) -> dict:
        return {
            "item_id": run.item.item_id,
            "accepted": False,
            "reason": reason,
            "challenge": "",
            "rounds_done": len(run.rounds),
            "target_rounds": run.target_rounds,
            "finished": True,
            "budget": _budget_view(entry),
        }

    @staticmethod
    def _verdict(entry: _Entry, verdict) -> dict:
        payload = to_dict(verdict)
        # 会话已结束，这时才把证据原文放出来供复盘；开局阶段一个字都不给。
        references: List[dict] = []
        for evidence_id in verdict.citation.supported:
            try:
                references.append(to_dict(entry.retriever.fetch(evidence_id)))
            except Exception:
                references.append({"evidence_id": evidence_id, "quote": "", "unavailable": True})
        payload["references"] = references
        return payload


def default_specs(count: int) -> List[ItemSpec]:
    specs: List[ItemSpec] = []
    for index in range(max(1, count)):
        topic, defect_type, level = DEFAULT_SPECS[index % len(DEFAULT_SPECS)]
        specs.append(
            ItemSpec(
                item_id="item-%d" % (index + 1),
                topic=topic,
                language="python",
                defect_type=defect_type,
                expected_level=level,
            )
        )
    return specs


def _find_run(handle, item_id: str) -> Optional[ItemRun]:
    return next((run for run in handle.runs if run.item.item_id == item_id), None)


def _budget_view(entry: _Entry) -> dict:
    budget = entry.handle.budget
    return {
        "cap": budget.cap,
        "total": budget.total,
        "remaining": budget.remaining,
        "reserve": RESERVE_CALLS,
        "cost_cny": budget.cost_cny,
        "offline_calls": entry.router.offline_calls,
    }
