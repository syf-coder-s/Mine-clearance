"""只读 RAGFlow 判例库 + 会话内原始材料与证据快照。

判例的字符偏移指向保存下来的片段原文，不伪装成源 Markdown 的文件偏移。
本题原始材料单独存放；不会把生成代码或学生答案上传到共享判例库。
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import time
import threading
import uuid
import urllib.error
import urllib.request
from dataclasses import asdict
from pathlib import Path
import re
from typing import Dict, List, Optional, Tuple, Sequence

from .base import IndexSealed, RAGError, RetrievedChunk, make_evidence_id
from .stub import LocalStubRAG


class RagflowRAG:
    _shared_query_cache: Dict[Tuple[object, ...], Tuple[float, Tuple[tuple, ...]]] = {}
    _shared_query_cache_lock = threading.Lock()

    def __init__(self, settings) -> None:
        self.base_url = settings.ragflow_base_url.rstrip("/")
        self.api_key = settings.ragflow_api_key
        configured_dataset_ids = [settings.ragflow_dataset_id]
        configured_dataset_ids.extend(
            getattr(settings, name, "")
            for name in (
                "ragflow_pattern_dataset_id",
                "ragflow_negative_dataset_id",
            )
        )
        self.dataset_ids = tuple(dict.fromkeys(
            dataset_id.strip() for dataset_id in configured_dataset_ids
            if isinstance(dataset_id, str) and dataset_id.strip()
        ))
        self.dataset_id = self.dataset_ids[0] if self.dataset_ids else ""
        self.dataset_roles = {self.dataset_id: "cases"} if self.dataset_id else {}
        for attribute, role in (
            ("ragflow_pattern_dataset_id", "patterns"),
            ("ragflow_negative_dataset_id", "negative_code"),
        ):
            dataset_id = getattr(settings, attribute, "")
            if dataset_id and dataset_id not in self.dataset_roles:
                self.dataset_roles[dataset_id] = role
        self.role_dataset_ids = {
            role: dataset_id for dataset_id, role in self.dataset_roles.items()
        }
        self.case_dataset_ids = tuple(
            dataset_id for dataset_id in self.dataset_ids
            if self.dataset_roles.get(dataset_id) == "cases"
        )
        if not self.base_url.startswith(("http://", "https://")):
            raise RAGError("RAGFLOW_BASE_URL 必须是完整的 HTTP 地址")
        if not self.api_key or not self.case_dataset_ids:
            raise RAGError("RAGFlow 接入需要 API Key 和知识库 ID")
        self.timeout_s = settings.ragflow_timeout_s
        self.cache_ttl_s = settings.ragflow_cache_ttl_s
        if not math.isfinite(self.cache_ttl_s) or self.cache_ttl_s < 0:
            raise RAGError("RAGFLOW_CACHE_TTL_S 必须是不小于 0 的有限数")
        self.case_top_k = settings.case_top_k
        if not 1 <= self.case_top_k <= 10:
            raise RAGError("CASE_TOP_K 必须在 1 到 10 之间")
        self.case_candidate_k = settings.case_candidate_k
        if not self.case_top_k <= self.case_candidate_k <= 50:
            raise RAGError("CASE_CANDIDATE_K 必须不小于 CASE_TOP_K 且不超过 50")
        self.case_min_similarity = settings.case_min_similarity
        self.pattern_candidate_k = settings.pattern_candidate_k
        self.pattern_min_similarity = settings.pattern_min_similarity
        self.negative_candidate_k = settings.negative_candidate_k
        self.negative_min_similarity = settings.negative_min_similarity
        for name, value in (
            ("CASE_MIN_SIMILARITY", self.case_min_similarity),
            ("PATTERN_MIN_SIMILARITY", self.pattern_min_similarity),
            ("NEGATIVE_MIN_SIMILARITY", self.negative_min_similarity),
        ):
            if not math.isfinite(value) or not 0.0 <= value <= 1.0:
                raise RAGError("%s 必须是 0 到 1 之间的有限数" % name)
        for name, value in (
            ("PATTERN_CANDIDATE_K", self.pattern_candidate_k),
            ("NEGATIVE_CANDIDATE_K", self.negative_candidate_k),
        ):
            if not 1 <= value <= 10:
                raise RAGError("%s 必须在 1 到 10 之间" % name)
        self.snapshot_dir = Path(settings.case_snapshot_dir)
        self.scope_id = "rag_" + uuid.uuid4().hex
        self.local = LocalStubRAG()
        self._case_chunks: Dict[str, RetrievedChunk] = {}
        self._source_spans: Dict[str, dict] = {}
        self._origins: Dict[str, dict] = {}
        self._queries: Dict[Tuple[str, int, Tuple[str, ...], float], Tuple[str, ...]] = {}
        self._snapshot_path = ""
        self.requests = 0
        self.connected = False
        self.last_error = ""
        self.rerank_stats = {"queries": 0, "candidates": 0, "selected": 0,
                             "type_matches": 0, "lexical_matches": 0,
                             "type_mismatches": 0, "mismatch_filtered": 0}
        self.retrieval_stats = {
            "requests_by_role": {}, "chunks_by_role": {},
            "selected_by_role": {}, "similarity_sum_by_role": {},
            "cache_hits_by_role": {}, "cache_misses_by_role": {},
            "empty_results_not_cached": 0,
        }
        self.quality_stats = {
            "duplicate_references": 0,
            "cross_document_duplicates": 0,
            "wrong_type_filtered": 0,
            "agent_reference_chars": 0,
            "agent_reference_count": 0,
            "agent_reference_chars_by_agent": {},
            "agent_reference_count_by_agent": {},
        }

    @property
    def sealed(self) -> bool:
        return self.local.sealed

    def index(self, doc_id: str, text: str, *, language: str = "text") -> int:
        if self.sealed:
            raise IndexSealed("会话证据已封存，不能写入")
        # 先清掉同名文档，防止幂等覆盖留下旧块和重复编号。
        for evidence_id in self.local.chunk_ids(doc_id):
            self._source_spans.pop(evidence_id, None)
        count = self.local.index(doc_id, text, language=language)
        for evidence_id in self.local.chunk_ids(doc_id):
            self._source_spans[evidence_id] = asdict(self.local.fetch(evidence_id))
        return count

    def retrieve(self, query: str, *, top_k: int = 10,
                 doc_id: Optional[str] = None) -> List[RetrievedChunk]:
        if self.sealed:
            raise IndexSealed("会话已封存，只允许按编号读取快照")
        if doc_id is not None:
            # 本题代码与共享判例不是同一文档，不能跨库替换本题证据。
            return self.local.retrieve(query, top_k=top_k, doc_id=doc_id)
        return self._retrieve_from_datasets(
            query, top_k, self.case_dataset_ids,
            similarity_threshold=self.case_min_similarity,
        )

    def _retrieve_from_datasets(self, query: str, top_k: int,
                                dataset_ids: Sequence[str], *,
                                similarity_threshold: float = 0.1) -> List[RetrievedChunk]:
        if self.sealed:
            raise IndexSealed("会话已封存，只允许按编号读取快照")
        if not query.strip() or not 1 <= top_k <= 50 or not dataset_ids:
            raise RAGError("查询不能为空，top_k 必须在 1 到 50 之间且知识库不可为空")
        key = (query, top_k, tuple(dataset_ids), float(similarity_threshold))
        if key in self._queries:
            return [self._case_chunks[eid] for eid in self._queries[key]]
        payload = {
            "question": query,
            "dataset_ids": list(dataset_ids),
            "page": 1,
            "page_size": top_k,
            "top_k": max(10, top_k),
            "similarity_threshold": similarity_threshold,
            "highlight": False,
            "use_kg": False,
        }
        cache_key = self._shared_cache_key(query, top_k, dataset_ids, similarity_threshold)
        cached_entries = self._shared_cache_get(cache_key)
        if cached_entries is not None:
            for dataset_id in dataset_ids:
                self._increment_stat("cache_hits_by_role", self.dataset_roles.get(dataset_id, "other"))
            results = self._materialize_entries(cached_entries, dataset_ids)
            self._queries[key] = tuple(c.evidence_id for c in results)
            return results
        for dataset_id in dataset_ids:
            self._increment_stat("cache_misses_by_role", self.dataset_roles.get(dataset_id, "other"))
        try:
            data = self._request("/api/v1/retrieval", payload)
            raw_chunks = data["chunks"]
            if not isinstance(raw_chunks, list):
                raise ValueError("chunks 必须是列表")
            entries = []
            for raw in raw_chunks:
                text = raw["content"]
                chunk_id = str(raw["id"])
                document_id = str(raw["document_id"])
                returned_dataset = str(raw.get("dataset_id", self.dataset_id))
                if returned_dataset not in dataset_ids:
                    raise ValueError("返回了指定知识库之外的片段")
                if not isinstance(text, str) or not text.strip():
                    raise ValueError("判例正文不能为空")
                score = float(raw.get("similarity", 0.0))
                if not math.isfinite(score):
                    raise ValueError("判例相关度不是有限数值")
                if score < similarity_threshold:
                    continue
                entries.append((text, chunk_id, document_id, returned_dataset, score))
                if len(entries) >= top_k:
                    break
            cached_entries = tuple(entries)
            self._shared_cache_put(cache_key, cached_entries)
            results = self._materialize_entries(cached_entries, dataset_ids)
            self._queries[key] = tuple(c.evidence_id for c in results)
            return results
        except (KeyError, TypeError, ValueError) as exc:
            self.last_error = "RAGFlow 判例返回结构不符合约定"
            raise RAGError(self.last_error) from exc

    def _materialize_entries(self, entries: Sequence[tuple], dataset_ids: Sequence[str]) -> List[RetrievedChunk]:
        results = []
        for text, chunk_id, document_id, returned_dataset, score in entries:
            if returned_dataset not in dataset_ids:
                raise RAGError("缓存返回了指定知识库之外的片段")
            digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
            snapshot_doc = "case:%s:%s:%s:%s" % (
                returned_dataset, document_id, chunk_id, digest[:16])
            evidence_id = make_evidence_id(snapshot_doc, 0, len(text))
            chunk = RetrievedChunk(evidence_id, snapshot_doc, chunk_id,
                                   text, 0, len(text), score)
            self._case_chunks[evidence_id] = chunk
            self._origins[evidence_id] = {
                "dataset_id": returned_dataset, "document_id": document_id,
                "chunk_id": chunk_id, "sha256": digest,
                "role": self.dataset_roles.get(returned_dataset, "other"),
            }
            role = self.dataset_roles.get(returned_dataset, "other")
            self._increment_stat("chunks_by_role", role)
            self.retrieval_stats["similarity_sum_by_role"][role] = (
                self.retrieval_stats["similarity_sum_by_role"].get(role, 0.0) + score
            )
            results.append(chunk)
        return results

    def _shared_cache_key(self, query: str, top_k: int,
                          dataset_ids: Sequence[str], similarity_threshold: float) -> Tuple[object, ...]:
        key_fingerprint = hashlib.sha256(self.api_key.encode("utf-8")).hexdigest()[:16]
        normalized_query = " ".join(query.split())
        return (self.base_url, key_fingerprint, normalized_query, top_k, tuple(dataset_ids),
                float(similarity_threshold))

    def _shared_cache_get(self, cache_key: Tuple[object, ...]) -> Optional[Tuple[tuple, ...]]:
        if self.cache_ttl_s <= 0:
            return None
        with self._shared_query_cache_lock:
            cached = self._shared_query_cache.get(cache_key)
            if cached is None:
                return None
            created, entries = cached
            if time.monotonic() - created > self.cache_ttl_s:
                self._shared_query_cache.pop(cache_key, None)
                return None
            return entries

    def _shared_cache_put(self, cache_key: Tuple[object, ...], entries: Tuple[tuple, ...]) -> None:
        if self.cache_ttl_s <= 0:
            return
        if not entries:
            self.retrieval_stats["empty_results_not_cached"] += 1
            return
        with self._shared_query_cache_lock:
            self._shared_query_cache[cache_key] = (time.monotonic(), entries)
            if len(self._shared_query_cache) > 256:
                oldest_key = min(self._shared_query_cache,
                                 key=lambda key: self._shared_query_cache[key][0])
                self._shared_query_cache.pop(oldest_key, None)

    @classmethod
    def clear_shared_cache(cls) -> None:
        with cls._shared_query_cache_lock:
            cls._shared_query_cache.clear()

    def prepare_cases(self, query: str, *, alternate_queries: Sequence[str] = ()) -> Tuple[str, ...]:
        # RAGFlow 负责向量候选；项目侧再按雷型和关键词重排，避免仅凭泛化语义
        # 把“等距比较”误配成“初始化错误”。原库只读，不改 RAGFlow 文档。
        queries = tuple(dict.fromkeys(q.strip() for q in (query, *alternate_queries) if q and q.strip()))
        if not queries:
            raise RAGError("判例查询不能为空")
        candidates = []
        for candidate_query in queries:
            candidates.extend(self.retrieve(candidate_query, top_k=self.case_candidate_k))
        candidates = self._deduplicate_candidates(candidates)
        merged_query = " ".join(queries)
        mismatch_before = self.rerank_stats.get("mismatch_filtered", 0)
        results = rerank_cases(merged_query, candidates, self.case_top_k,
                               stats=self.rerank_stats)
        self.quality_stats["wrong_type_filtered"] += (
            self.rerank_stats.get("mismatch_filtered", 0) - mismatch_before
        )
        if not results:
            self.last_error = "RAGFlow 未召回相关判例；本场未启动，不使用本地桩冒充"
            raise RAGError(self.last_error)
        for evidence_id in dict.fromkeys(chunk.evidence_id for chunk in results):
            role = self._origins.get(evidence_id, {}).get("role", "other")
            self._increment_stat("selected_by_role", role)
        return tuple(dict.fromkeys(chunk.evidence_id for chunk in results))

    def prepare_auxiliary(self, query: str, *, expected_code: str) -> Dict[str, Tuple[str, ...]]:
        """分开召回规则摘要和正确代码反例，避免混成正向判例。"""
        result = {"patterns": (), "negative_code": ()}
        if not query.strip() or not re.fullmatch(r"R\d{2}", expected_code, re.I):
            return result
        auxiliary_query = expected_code.upper() + " " + query
        for role in result:
            dataset_id = self.role_dataset_ids.get(role)
            if not dataset_id:
                continue
            try:
                if role == "patterns":
                    candidate_k = self.pattern_candidate_k
                    min_similarity = self.pattern_min_similarity
                else:
                    candidate_k = self.negative_candidate_k
                    min_similarity = self.negative_min_similarity
                candidates = self._retrieve_from_datasets(
                    auxiliary_query, candidate_k, (dataset_id,),
                    similarity_threshold=min_similarity,
                )
                candidates = self._deduplicate_candidates(candidates)
                matching = []
                for chunk in candidates:
                    header = chunk.text.splitlines()[0][:240] if chunk.text.splitlines() else chunk.text[:240]
                    if re.search(r"R\d{2}", header, re.I) and not re.search(
                        r"(?<![A-Z0-9])" + re.escape(expected_code) + r"(?![A-Z0-9])",
                        header, re.I,
                    ):
                        self.quality_stats["wrong_type_filtered"] += 1
                        continue
                    if re.search(r"(?<![A-Z0-9])" + re.escape(expected_code) + r"(?![A-Z0-9])", header, re.I):
                        matching.append(chunk)
                selected = rerank_cases(auxiliary_query, matching, 1)
                if selected:
                    result[role] = (selected[0].evidence_id,)
                    self._increment_stat("selected_by_role", role)
            except RAGError as exc:
                # 辅助库不可用时保留主判例链，不伪装成命中，也不阻断出题。
                self.last_error = str(exc)
        return result

    def fetch(self, evidence_id: str):
        if evidence_id in self._case_chunks:
            return self._case_chunks[evidence_id].to_span()
        return self.local.fetch(evidence_id)

    def seal(self) -> None:
        if self.sealed:
            return
        # 每个检索器对应独立会话；只冻结快照，不冻结整个共享 RAGFlow 库。
        destination = self.snapshot_dir / (self.scope_id + ".json")
        temporary = destination.with_suffix(".tmp")
        snapshot = {
            "scope_id": self.scope_id, "dataset_id": self.dataset_id,
            "source_evidence": self._source_spans,
            "case_evidence": {eid: asdict(chunk.to_span())
                              for eid, chunk in self._case_chunks.items()},
            "provenance": self._origins,
        }
        try:
            self.snapshot_dir.mkdir(parents=True, exist_ok=True)
            temporary.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2),
                                 encoding="utf-8")
            os.replace(temporary, destination)
        except OSError as exc:
            raise RAGError("无法保存会话证据快照") from exc
        self._snapshot_path = str(destination)
        self.local.seal()

    def summary(self) -> dict:
        return {
            "backend": "RagflowRAG", "dataset_id": self.dataset_id,
            "dataset_ids": list(self.dataset_ids),
            "dataset_roles": dict(self.dataset_roles),
            "source_material": "local_structural_chunks",
            "case_library": "ragflow", "connected": self.connected,
            "degraded": False, "last_error": self.last_error,
            "sealed": self.sealed, "case_chunks": len(self._case_chunks),
            "retrieval_requests": self.requests,
            "snapshot_saved": bool(self._snapshot_path),
            "case_candidate_k": self.case_candidate_k,
            "pattern_candidate_k": self.pattern_candidate_k,
            "negative_candidate_k": self.negative_candidate_k,
            "pattern_min_similarity": self.pattern_min_similarity,
            "negative_min_similarity": self.negative_min_similarity,
            "ragflow_cache_ttl_s": self.cache_ttl_s,
            "case_query_count": len(self._queries),
            "case_rerank": dict(self.rerank_stats),
            "retrieval_stats": self._retrieval_stats_snapshot(),
            "quality_stats": self._quality_stats_snapshot(),
        }

    def _increment_stat(self, bucket: str, role: str) -> None:
        values = self.retrieval_stats[bucket]
        values[role] = values.get(role, 0) + 1

    def _retrieval_stats_snapshot(self) -> dict:
        chunks = self.retrieval_stats["chunks_by_role"]
        sums = self.retrieval_stats["similarity_sum_by_role"]
        averages = {
            role: round(sums[role] / count, 4)
            for role, count in chunks.items() if count
        }
        return {
            "requests_by_role": dict(self.retrieval_stats["requests_by_role"]),
            "chunks_by_role": dict(chunks),
            "selected_by_role": dict(self.retrieval_stats["selected_by_role"]),
            "average_similarity_by_role": averages,
            "cache_hits_by_role": dict(self.retrieval_stats["cache_hits_by_role"]),
            "cache_misses_by_role": dict(self.retrieval_stats["cache_misses_by_role"]),
            "empty_results_not_cached": self.retrieval_stats["empty_results_not_cached"],
        }

    def _quality_stats_snapshot(self) -> dict:
        """返回不会暴露参考正文的质量与提示词用量统计。"""
        return {
            "duplicate_references": self.quality_stats["duplicate_references"],
            "cross_document_duplicates": self.quality_stats["cross_document_duplicates"],
            "wrong_type_filtered": self.quality_stats["wrong_type_filtered"],
            "agent_reference_chars": self.quality_stats["agent_reference_chars"],
            "agent_reference_count": self.quality_stats["agent_reference_count"],
            "agent_reference_chars_by_agent": dict(
                self.quality_stats["agent_reference_chars_by_agent"]
            ),
            "agent_reference_count_by_agent": dict(
                self.quality_stats["agent_reference_count_by_agent"]
            ),
        }

    def _deduplicate_candidates(self, candidates: Sequence[RetrievedChunk]) -> List[RetrievedChunk]:
        """同一批跨查询/跨文档候选按正文指纹去重，保留相似度最高者。"""
        chosen: Dict[str, Tuple[int, RetrievedChunk]] = {}
        for chunk in candidates:
            digest = hashlib.sha256(chunk.text.encode("utf-8")).hexdigest()
            previous = chosen.get(digest)
            if previous is None:
                chosen[digest] = (len(chosen), chunk)
                continue
            self.quality_stats["duplicate_references"] += 1
            if previous[1].doc_id != chunk.doc_id:
                self.quality_stats["cross_document_duplicates"] += 1
            old = previous[1]
            if (chunk.score, chunk.chunk_id) > (old.score, old.chunk_id):
                chosen[digest] = (previous[0], chunk)
        return [chunk for _, chunk in sorted(chosen.values(), key=lambda pair: pair[0])]

    def record_agent_reference_usage(self, agent: str, references: Sequence[str]) -> None:
        """记录最终拼入 Agent 提示词的参考行长度，不记录参考正文。"""
        name = str(agent or "unknown")
        reference_list = tuple(references)
        count = len(reference_list)
        chars = sum(len(str(reference)) for reference in reference_list)
        self.quality_stats["agent_reference_count"] += count
        self.quality_stats["agent_reference_chars"] += chars
        by_agent_count = self.quality_stats["agent_reference_count_by_agent"]
        by_agent_chars = self.quality_stats["agent_reference_chars_by_agent"]
        by_agent_count[name] = by_agent_count.get(name, 0) + count
        by_agent_chars[name] = by_agent_chars.get(name, 0) + chars

    def _request(self, path: str, payload: dict) -> dict:
        request = urllib.request.Request(
            self.base_url + path,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json",
                     "Authorization": "Bearer " + self.api_key}, method="POST")
        self.requests += 1
        for dataset_id in payload.get("dataset_ids", ()):
            role = self.dataset_roles.get(dataset_id, "other")
            self._increment_stat("requests_by_role", role)
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_s) as response:
                result = json.loads(response.read().decode("utf-8"))
            if not isinstance(result, dict) or result.get("code") != 0:
                raise ValueError("RAGFlow 返回业务错误")
            if not isinstance(result.get("data"), dict):
                raise ValueError("RAGFlow 缺少 data 对象")
            self.connected = True
            self.last_error = ""
            return result["data"]
        except (urllib.error.URLError, TimeoutError, ValueError, OSError) as exc:
            self.connected = False
            self.last_error = "RAGFlow 检索失败（%s）" % type(exc).__name__
            raise RAGError(self.last_error) from exc


# ---- 判例重排（纯本地、无额外网络调用） ----

_TYPE_TERMS = {
    "boundary": ("边界", "空输入", "空列表", "单元素", "越界", "等距", "比较", "极端", "范围"),
    "logic": ("逻辑", "方向", "不变量", "分支", "等价", "语义"),
    "api_misuse": ("api", "接口", "参数", "分页", "状态码", "调用", "协议"),
    "data_leak": ("泄漏", "隐私", "手机号", "密码", "日志", "敏感", "个人信息"),
    "type_confusion": ("类型", "字符串", "整数", "空值", "null", "none", "转换"),
    "security": ("安全", "注入", "权限", "认证", "越权", "密码"),
    "perf": ("性能", "复杂度", "超时", "内存", "循环", "效率"),
    "doc_mismatch": ("文档", "约定", "说明", "语义", "规范"),
}

_TYPE_CODES = {
    "boundary": ("R02",),
    "logic": ("R06",),
    "api_misuse": ("R01",),
    "data_leak": ("R07",),
    "type_confusion": ("R05",),
    "security": ("R08",),
    "perf": ("R03", "R09"),
    "doc_mismatch": ("R06",),
}


def _tokens(text: str) -> set:
    """中英文混合的轻量 token；不引入分词依赖，避免改变部署镜像。"""
    lowered = text.lower()
    words = set(re.findall(r"[a-z][a-z0-9_]{1,}|\d+", lowered))
    for term in set(sum((list(v) for v in _TYPE_TERMS.values()), [])):
        if term in lowered:
            words.add(term)
    return words


def _query_type(query: str) -> str:
    lowered = query.lower()
    # as_query() 会把枚举值直接放入查询，优先相信显式类型，
    # 避免“等距逻辑”因中文关键词先命中 boundary。
    for defect_type in _TYPE_TERMS:
        if re.search(r"(?<![a-z0-9_])" + re.escape(defect_type) + r"(?![a-z0-9_])", lowered):
            return defect_type
    for defect_type, terms in _TYPE_TERMS.items():
        if defect_type in lowered or any(term in lowered for term in terms):
            return defect_type
    return ""


def rerank_cases(query: str, candidates: Sequence[RetrievedChunk], top_k: int,
                 *, stats: Optional[dict] = None) -> List[RetrievedChunk]:
    """先向量召回，再做可解释的本地重排。

    分数不是新的概率：只用于同一批候选的排序。基础相似度占 55%，关键词占 30%，
    雷型匹配占 15%；权重集中在此处，后续可用标注集调参而不改协议。
    """
    if top_k <= 0:
        return []
    query_tokens = _tokens(query)
    defect_type = _query_type(query)
    scored = []
    seen = set()
    local_stats = stats if stats is not None else {}
    local_stats["queries"] = local_stats.get("queries", 0) + 1
    local_stats["candidates"] = local_stats.get("candidates", 0) + len(candidates)
    for chunk in candidates:
        if chunk.evidence_id in seen:
            continue
        seen.add(chunk.evidence_id)
        text = chunk.text.lower()
        overlap = len(query_tokens & _tokens(text)) / max(1, len(query_tokens))
        # 判例正文反复出现“学生主张/后果”等通用词，不能用全文命中；
        # 优先看“雷型:”首段和前 240 字的关键标签，避免所有样本被误判为同一类。
        header = text.splitlines()[0][:240] if text.splitlines() else text[:240]
        matched_code = next((code for code in sum(_TYPE_CODES.values(), ())
                             if code.lower() in header), "")
        type_hit = bool(defect_type and (
            any(code.lower() in header for code in _TYPE_CODES.get(defect_type, ())) or
            any(term in header for term in _TYPE_TERMS[defect_type])
        ))
        base = max(0.0, min(1.0, float(chunk.score)))
        mismatch = bool(defect_type and matched_code and
                        matched_code not in _TYPE_CODES.get(defect_type, ()))
        final = (0.55 * base + 0.30 * min(1.0, overlap * 2.0)
                 + 0.15 * float(type_hit) - 0.12 * float(mismatch))
        local_stats["type_matches"] = local_stats.get("type_matches", 0) + int(type_hit)
        local_stats["lexical_matches"] = local_stats.get("lexical_matches", 0) + int(overlap > 0)
        local_stats["type_mismatches"] = local_stats.get("type_mismatches", 0) + int(mismatch)
        scored.append((final, base, chunk))
    # 有明确 Rxx 标签时，若同批存在正确雷型，剔除其他雷型，避免语义相似把相邻缺陷带进模型。
    if defect_type:
        compatible = [row for row in scored if not (
            re.search(r"R\d{2}", row[2].text[:240], re.I)
            and _explicit_type_mismatch(defect_type, row[2].text[:240])
        )]
        if compatible:
            local_stats["mismatch_filtered"] = local_stats.get("mismatch_filtered", 0) + len(scored) - len(compatible)
            scored = compatible
    scored.sort(key=lambda row: (-row[0], -row[1], row[2].chunk_id))
    selected = [row[2] for row in scored[:top_k]]
    local_stats["selected"] = local_stats.get("selected", 0) + len(selected)
    return selected


def _explicit_type_mismatch(defect_type: str, header: str) -> bool:
    """只依据标题中的明确 Rxx 判断冲突，不拿正文中提到的其他雷型误杀。"""
    codes = _TYPE_CODES.get(defect_type, ())
    found = re.search(r"R\d{2}", header, re.IGNORECASE)
    return bool(found and found.group(0).upper() not in codes)
