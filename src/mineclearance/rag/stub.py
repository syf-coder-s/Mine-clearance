"""本地检索桩。

用途：没有后端、没有网络时把链路跑通，以及给学生一份可读的参考实现。
打分故意做得朴素（字面重叠 + 子串命中），不冒充向量检索：
    真后端接上之后，召回策略由 teams 在 RAG 侧调，这里只保证契约一致。
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional

from ..schemas import EvidenceSpan
from . import chunking
from .base import IndexSealed, RAGError, RetrievedChunk, make_evidence_id, rank_and_cut

_LATIN = re.compile(r"[A-Za-z_][A-Za-z0-9_]{1,}")
_CJK = re.compile(r"[\u4e00-\u9fff]")


def _terms(text: str) -> List[str]:
    lowered = text.lower()
    terms = [m.group(0).lower() for m in _LATIN.finditer(lowered)]
    han = _CJK.findall(text)
    terms.extend("".join(han[i : i + 2]) for i in range(max(0, len(han) - 1)))
    return terms


def _positional(pool: List[RetrievedChunk], top_k: int) -> List[RetrievedChunk]:
    """按文档内位置返回。只在字面召回为空时兜底，分数一律 0，不假装是相关性。"""
    ordered = sorted(pool, key=lambda c: (c.doc_id, c.char_start))
    return ordered[: max(0, top_k)]


class LocalStubRAG:
    def __init__(self) -> None:
        self._chunks: Dict[str, RetrievedChunk] = {}
        self._by_doc: Dict[str, List[str]] = {}
        self._sealed = False

    # ---- 写 ----

    def index(self, doc_id: str, text: str, *, language: str = "text") -> int:
        if self._sealed:
            raise IndexSealed("索引已封印，不能再写入文档: %s" % doc_id)
        if not doc_id:
            raise RAGError("doc_id 不能为空")
        for old_id in self._by_doc.pop(doc_id, []):
            self._chunks.pop(old_id, None)
        spans = chunking.split(text, language)
        stored = 0
        for start, end in spans:
            quote = text[start:end]
            evidence_id = make_evidence_id(doc_id, start, end)
            self._chunks[evidence_id] = RetrievedChunk(
                evidence_id=evidence_id,
                doc_id=doc_id,
                chunk_id=chunking.chunk_id(doc_id, start, end),
                text=quote,
                char_start=start,
                char_end=end,
            )
            self._by_doc.setdefault(doc_id, []).append(evidence_id)
            stored += 1
        return stored

    # ---- 读 ----

    def retrieve(
        self, query: str, *, top_k: int = 10, doc_id: Optional[str] = None
    ) -> List[RetrievedChunk]:
        if self._sealed:
            raise IndexSealed("索引已封印：只允许按 evidence_id 取回，不允许重新检索")
        # doc_id 是「只在这份文档里找」。预取阶段必须带上它，否则会召回别的题的证据，
        # 学生点开引用看到的是另一道题的代码。
        pool = [c for c in self._chunks.values() if doc_id is None or c.doc_id == doc_id]
        query_terms = _terms(query)
        if not query_terms:
            return _positional(pool, top_k)
        scored: List[RetrievedChunk] = []
        for chunk in pool:
            chunk_terms = set(_terms(chunk.text))
            hits = sum(1 for term in query_terms if term in chunk_terms)
            if hits == 0:
                continue
            score = hits / len(query_terms)
            scored.append(
                RetrievedChunk(
                    evidence_id=chunk.evidence_id,
                    doc_id=chunk.doc_id,
                    chunk_id=chunk.chunk_id,
                    text=chunk.text,
                    char_start=chunk.char_start,
                    char_end=chunk.char_end,
                    score=round(score, 4),
                )
            )
        if not scored:
            # 冷启动兜底：查询是中文、文档是代码时，字面重叠必然为 0。
            # 桩在这里退化为「按位置返回」，只为保证离线联调时预取不为空；
            # 真后端（向量或混合召回）不需要这个分支。
            return _positional(pool, top_k)
        return rank_and_cut(scored, top_k)

    def fetch(self, evidence_id: str) -> EvidenceSpan:
        chunk = self._chunks.get(evidence_id)
        if chunk is None:
            raise RAGError("证据不存在: %s" % evidence_id)
        return chunk.to_span()

    def chunk_ids(self, doc_id: str) -> List[str]:
        return list(self._by_doc.get(doc_id, ()))

    def doc_ids(self) -> List[str]:
        return list(self._by_doc)

    # ---- 封印 ----

    def seal(self) -> None:
        self._sealed = True

    @property
    def sealed(self) -> bool:
        return self._sealed
