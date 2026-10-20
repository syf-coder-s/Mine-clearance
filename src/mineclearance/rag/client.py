"""HTTP 检索客户端 + 降级包装。

契约写在 docs/rag-api.md，这里是它的唯一实现。两个设计取舍：
    1. 只用标准库，超时 2 秒。检索挂在关键路径上，慢一次就把整场的 15 分钟吃掉一块。
    2. 后端连不上时**不中断会话**，自动降级到本地桩并置 degraded 标记。
       现场演示最怕「后端没起」，而排雷兵的主链不该因为检索缺席就整场崩掉。
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import List, Optional, Sequence, Tuple

from ..schemas import EvidenceSpan
from .base import IndexSealed, RAGError, RetrievedChunk, SealedView
from .stub import LocalStubRAG


class HttpRAG:
    def __init__(self, base_url: str, api_key: str = "", *, timeout_s: float = 2.0, retries: int = 1) -> None:
        if not base_url:
            raise RAGError("RAG_BASE_URL 为空，不应构造 HttpRAG")
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout_s = timeout_s
        self.retries = retries
        self._sealed = False

    # ---- 写 ----

    def index(self, doc_id: str, text: str, *, language: str = "text") -> int:
        if self._sealed:
            raise IndexSealed("索引已封印，不能再写入文档: %s" % doc_id)
        body = self._request("POST", "/v1/index", {"doc_id": doc_id, "text": text, "language": language})
        return int(body.get("chunks", 0))

    # ---- 读 ----

    def retrieve(
        self, query: str, *, top_k: int = 10, doc_id: Optional[str] = None
    ) -> List[RetrievedChunk]:
        if self._sealed:
            raise IndexSealed("索引已封印：只允许按 evidence_id 取回，不允许重新检索")
        payload = {"query": query, "top_k": top_k}
        if doc_id:
            payload["doc_id"] = doc_id
        body = self._request("POST", "/v1/retrieve", payload)
        chunks: List[RetrievedChunk] = []
        for entry in body.get("items", []):
            try:
                chunks.append(
                    RetrievedChunk(
                        evidence_id=entry["evidence_id"],
                        doc_id=entry["doc_id"],
                        chunk_id=entry.get("chunk_id", ""),
                        text=entry["text"],
                        char_start=int(entry["char_start"]),
                        char_end=int(entry["char_end"]),
                        score=float(entry.get("score", 0.0)),
                    )
                )
            except (KeyError, TypeError, ValueError) as exc:
                raise RAGError("检索返回体不合契约: %s" % exc) from exc
        return chunks

    def fetch(self, evidence_id: str) -> EvidenceSpan:
        body = self._request("GET", "/v1/evidence/" + evidence_id, None)
        try:
            return EvidenceSpan(
                evidence_id=body["evidence_id"],
                doc_id=body["doc_id"],
                chunk_id=body.get("chunk_id", ""),
                char_start=int(body["char_start"]),
                char_end=int(body["char_end"]),
                quote=body["quote"],
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise RAGError("证据返回体不合契约: %s" % exc) from exc

    def seal(self) -> None:
        if self._sealed:
            return
        self._request("POST", "/v1/seal", {})
        self._sealed = True

    @property
    def sealed(self) -> bool:
        return self._sealed

    # ---- 传输 ----

    def _request(self, method: str, path: str, payload: Optional[dict]):
        data = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = "Bearer " + self.api_key
        last_error: Optional[Exception] = None
        for _ in range(self.retries + 1):
            request = urllib.request.Request(self.base_url + path, data=data, headers=headers, method=method)
            try:
                with urllib.request.urlopen(request, timeout=self.timeout_s) as response:
                    raw = response.read().decode("utf-8")
                    return json.loads(raw) if raw.strip() else {}
            except urllib.error.HTTPError as exc:
                detail = exc.read().decode("utf-8", "replace")[:300]
                raise RAGError("检索后端 %d: %s" % (exc.code, detail)) from exc
            except (urllib.error.URLError, TimeoutError, ValueError) as exc:
                last_error = exc
        raise RAGError("连不上检索后端 %s: %s" % (self.base_url, last_error))


class ResilientRAG:
    """主后端 + 本地桩的降级壳。

    降级发生在第一次失败时，之后整场都用桩，并且把先前写过的文档重放进桩，
    避免「前半场命中、后半场全空」这种更难看的状态。
    """

    def __init__(self, primary, fallback: Optional[LocalStubRAG] = None) -> None:
        self.primary = primary
        self.fallback = fallback or LocalStubRAG()
        self.degraded = False
        self.degrade_reason = ""
        self._docs: List[Tuple[str, str, str]] = []

    def index(self, doc_id: str, text: str, *, language: str = "text") -> int:
        self._docs.append((doc_id, text, language))
        if self.degraded:
            return self.fallback.index(doc_id, text, language=language)
        try:
            return self.primary.index(doc_id, text, language=language)
        except RAGError as exc:
            self._degrade(exc)
            return self.fallback.index(doc_id, text, language=language)

    def retrieve(
        self, query: str, *, top_k: int = 10, doc_id: Optional[str] = None
    ) -> List[RetrievedChunk]:
        if self.degraded:
            return self.fallback.retrieve(query, top_k=top_k, doc_id=doc_id)
        try:
            return self.primary.retrieve(query, top_k=top_k, doc_id=doc_id)
        except RAGError as exc:
            self._degrade(exc)
            return self.fallback.retrieve(query, top_k=top_k, doc_id=doc_id)

    def fetch(self, evidence_id: str) -> EvidenceSpan:
        if self.degraded:
            return self.fallback.fetch(evidence_id)
        try:
            return self.primary.fetch(evidence_id)
        except RAGError as exc:
            self._degrade(exc)
            return self.fallback.fetch(evidence_id)

    def seal(self) -> None:
        if not self.degraded:
            try:
                self.primary.seal()
            except RAGError as exc:
                self._degrade(exc)
        self.fallback.seal()

    @property
    def sealed(self) -> bool:
        return self.fallback.sealed

    def view(self) -> SealedView:
        return SealedView(self)

    def _degrade(self, exc: Exception) -> None:
        if self.degraded:
            return
        self.degraded = True
        self.degrade_reason = str(exc)[:200]
        for doc_id, text, language in self._docs:
            self.fallback.index(doc_id, text, language=language)

    def summary(self) -> dict:
        return {
            "backend": type(self.primary).__name__,
            "degraded": self.degraded,
            "degrade_reason": self.degrade_reason,
            "sealed": self.sealed,
        }
