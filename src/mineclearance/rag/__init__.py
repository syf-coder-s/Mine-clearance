"""检索层入口。

build_retriever() 是唯一该被调用的构造器：
    配了 RAG_BASE_URL 就走 HTTP（外面套降级壳），没配就用本地桩。
    不要在别处直接 new HttpRAG，否则预取、封印、降级三件事会漏掉。
"""

from .base import (
    IndexSealed,
    RAGError,
    Retriever,
    RetrievedChunk,
    SealedView,
    as_query,
    compact_reference,
    make_evidence_id,
    rank_and_cut,
)
from .client import HttpRAG, ResilientRAG
from .stub import LocalStubRAG


def build_retriever(settings) -> Retriever:
    if settings.rag_provider.strip().lower() == "ragflow":
        from .ragflow import RagflowRAG
        return RagflowRAG(settings)
    if not settings.rag_base_url:
        return LocalStubRAG()
    return ResilientRAG(
        HttpRAG(settings.rag_base_url, settings.rag_api_key, timeout_s=settings.rag_timeout_s)
    )


__all__ = [
    "Retriever",
    "RetrievedChunk",
    "SealedView",
    "RAGError",
    "IndexSealed",
    "LocalStubRAG",
    "HttpRAG",
    "ResilientRAG",
    "build_retriever",
    "make_evidence_id",
    "as_query",
    "compact_reference",
    "rank_and_cut",
]
