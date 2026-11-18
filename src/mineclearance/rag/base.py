"""检索层的契约。

三条铁律在代码里的落点：
    一 · 检索一次即冻结。seal() 之后 retrieve() 直接抛错，不给「再查一次」留口子。
    二 · 学生产出永不入库。index() 的入参只有 doc_id 与原文，没有「作答」这个字段，
         所以从类型上就不存在把学生答案写进索引的路径。
    三 · 切分跟着雷走。切分器在 chunking.py，代码按函数、数据按表、文章按小节。
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import List, Optional, Protocol, Sequence, runtime_checkable

from ..schemas import EvidenceSpan


def compact_reference(text: str, max_chars: int = 900) -> str:
    """压缩内部参考，保留雷型标题和判级关键词，避免把整篇他题代码送进模型。"""
    if max_chars < 80:
        raise ValueError("max_chars 必须至少为 80")
    normalized = " ".join(str(text).split())
    if len(normalized) <= max_chars:
        return normalized
    head_budget = max(40, max_chars // 3)
    keyword_pattern = re.compile(
        r"R\d{2}|L[0-4]|判级|依据|关键|触发|错误|边界|误报|正确|修复|API|复杂度",
        re.IGNORECASE,
    )
    tail_budget = min(90, max_chars // 3)
    tail = normalized[-tail_budget:]
    sentences = [part.strip() for part in re.split(r"(?<=[。；.!?])\s*", normalized) if part.strip()]
    keyword_hits = []
    for sentence in sentences:
        if keyword_pattern.search(sentence) and sentence not in keyword_hits:
            keyword_hits.append(sentence[:110])
    middle = "；".join(keyword_hits[:3])
    fixed = len(" …  … ") + len(middle) + len(tail)
    head_budget = max(40, max_chars - fixed)
    head = normalized[:head_budget]
    result = head + " … " + middle + " … " + tail
    if len(result) > max_chars:
        result = result[: max_chars - tail_budget - 3] + " … " + tail
    return result[:max_chars]


class RAGError(RuntimeError):
    """检索后端的一般性错误（超时、5xx、返回体不合契约）。"""


class IndexSealed(RuntimeError):
    """封印之后仍试图改索引或重新检索。这是设计违规，不是运行时异常。"""


def make_evidence_id(doc_id: str, char_start: int, char_end: int) -> str:
    """证据 id 由位置决定，重跑一次仍然是同一个 id，方便核验引用。"""
    raw = "%s\x00%d\x00%d" % (doc_id, char_start, char_end)
    return "ev_" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]


@dataclass(frozen=True)
class RetrievedChunk:
    evidence_id: str
    doc_id: str
    chunk_id: str
    text: str
    char_start: int
    char_end: int
    score: float = 0.0

    def to_span(self) -> EvidenceSpan:
        return EvidenceSpan(
            evidence_id=self.evidence_id,
            doc_id=self.doc_id,
            chunk_id=self.chunk_id,
            char_start=self.char_start,
            char_end=self.char_end,
            quote=self.text,
        )


@runtime_checkable
class Retriever(Protocol):
    def index(self, doc_id: str, text: str, *, language: str = "text") -> int:
        """写入一份文档，返回切出来的块数。只在离线阶段调用。"""

    def retrieve(self, query: str, *, top_k: int = 10, doc_id: Optional[str] = None) -> List[RetrievedChunk]:
        """召回。封印后调用即违规。

        doc_id 给定时只在该文档内召回。预取阶段必须给，
        否则会召回别的题的片段，引用就指向了错的代码。
        """

    def fetch(self, evidence_id: str) -> EvidenceSpan:
        """按 id 取回已封存的片段。这是封印之后唯一的读路径。"""

    def seal(self) -> None:
        """冻结索引。幂等。"""

    @property
    def sealed(self) -> bool: ...


class SealedView:
    """给在线阶段的只读视图。

    把它交给裁判和对抗方，而不是把 Retriever 整个递过去——这样「再查一次」
    在类型层面就写不出来，只能按 id 取。
    """

    def __init__(self, retriever: Retriever) -> None:
        self._retriever = retriever

    def fetch(self, evidence_id: str) -> EvidenceSpan:
        return self._retriever.fetch(evidence_id)

    def fetch_many(self, evidence_ids: Sequence[str]) -> List[EvidenceSpan]:
        spans = []
        for evidence_id in evidence_ids:
            try:
                spans.append(self._retriever.fetch(evidence_id))
            except RAGError:
                continue
        return spans

    def record_reference_usage(self, agent: str, references: Sequence[str]) -> None:
        """可选的只写统计钩子；没有统计实现的检索器保持兼容。"""
        recorder = getattr(self._retriever, "record_agent_reference_usage", None)
        if callable(recorder):
            recorder(agent, references)


def rank_and_cut(chunks: Sequence[RetrievedChunk], top_k: int, *, min_score: float = 0.0) -> List[RetrievedChunk]:
    """排序后截断。召回 8–12，进裁判的只留 3，这一步在本地做，不发请求。"""
    ordered = [c for c in chunks if c.score >= min_score]
    ordered.sort(key=lambda c: (-c.score, c.char_start))
    return ordered[: max(0, top_k)]


def as_query(item_title: str, defect_type: str, language: str = "", context: str = "") -> str:
    """检索查询串。不做在线查询改写，拼一次就定稿。"""
    parts: List[str] = [item_title, defect_type]
    if language:
        parts.append(language)
    if context and context.strip():
        # context 只来自内部题目 diff/rubric，不接收学生输入；截断避免把整段代码塞进检索。
        parts.append(" ".join(context.strip().split())[:500])
    return " ".join(p for p in parts if p)


def optional_span(view: SealedView, evidence_id: str) -> Optional[EvidenceSpan]:
    try:
        return view.fetch(evidence_id)
    except RAGError:
        return None
