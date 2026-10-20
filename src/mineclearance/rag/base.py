"""检索层的契约。

三条铁律在代码里的落点：
    一 · 检索一次即冻结。seal() 之后 retrieve() 直接抛错，不给「再查一次」留口子。
    二 · 学生产出永不入库。index() 的入参只有 doc_id 与原文，没有「作答」这个字段，
         所以从类型上就不存在把学生答案写进索引的路径。
    三 · 切分跟着雷走。切分器在 chunking.py，代码按函数、数据按表、文章按小节。
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import List, Optional, Protocol, Sequence, runtime_checkable

from ..schemas import EvidenceSpan


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


def rank_and_cut(chunks: Sequence[RetrievedChunk], top_k: int, *, min_score: float = 0.0) -> List[RetrievedChunk]:
    """排序后截断。召回 8–12，进裁判的只留 3，这一步在本地做，不发请求。"""
    ordered = [c for c in chunks if c.score >= min_score]
    ordered.sort(key=lambda c: (-c.score, c.char_start))
    return ordered[: max(0, top_k)]


def as_query(item_title: str, defect_type: str, language: str = "") -> str:
    """检索查询串。不做在线查询改写，拼一次就定稿。"""
    parts: List[str] = [item_title, defect_type]
    if language:
        parts.append(language)
    return " ".join(p for p in parts if p)


def optional_span(view: SealedView, evidence_id: str) -> Optional[EvidenceSpan]:
    try:
        return view.fetch(evidence_id)
    except RAGError:
        return None
