"""验证原生协议、会话隔离和在线只读，不依赖真实密钥。"""
from __future__ import annotations

import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from tests.test_rag import _Server, ALPHA, BETA
from mineclearance.api.store import (
    SessionStore, CitationOutsideAnchor, EvidenceForbidden, UpstreamError,
)
from mineclearance.config import Settings
from mineclearance.llm.mock import MockLLM
from mineclearance.rag import RAGError, IndexSealed, LocalStubRAG, compact_reference
from mineclearance.rag.ragflow import RagflowRAG, rerank_cases
from mineclearance.rag.base import RetrievedChunk

CASE_TEXT = "内部判例唯一标记：边界相等时应核验返回值，标准答案仅供判级参考。"


def native_response(method, path, body):
    if method != "POST" or path != "/api/v1/retrieval":
        return 404, {}
    return 200, {"code": 0, "data": {"chunks": [{
        "id": "chunk-1", "document_id": "document-1", "dataset_id": "dataset-test",
        "content": CASE_TEXT, "similarity": 0.8,
    }]}}


class RagflowTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        RagflowRAG.clear_shared_cache()

    def settings(self, url):
        return Settings(llm_provider="mock", rag_provider="ragflow",
                        ragflow_base_url=url, ragflow_api_key="secret-test-key",
                        ragflow_dataset_id="dataset-test",
                        case_snapshot_dir=self.directory.name)

    def test_native_contract_and_source_isolation(self):
        with _Server(native_response) as server:
            rag = RagflowRAG(self.settings(server.url))
            rag.index("doc_a", ALPHA, language="python")
            source = rag.retrieve("alpha", doc_id="doc_a")[0]
            self.assertEqual(source.doc_id, "doc_a")
            self.assertEqual(server.calls, [])
            case = rag.prepare_cases("边界")
            self.assertEqual(rag.prepare_cases("边界"), case)
            self.assertEqual(len(server.calls), 1)
            call = server.calls[0]
            self.assertEqual(call["auth"], "Bearer secret-test-key")
            self.assertEqual(call["body"]["dataset_ids"], ["dataset-test"])
            self.assertEqual(rag.fetch(case[0]).quote, CASE_TEXT)
            self.assertNotEqual(source.evidence_id, case[0])

    def test_dual_query_merges_candidates_and_caches_each_query(self):
        with _Server(native_response) as server:
            rag = RagflowRAG(self.settings(server.url))
            case = rag.prepare_cases("题目语义 boundary", alternate_queries=("<= 等距比较 boundary",))
            self.assertTrue(case)
            self.assertEqual(len(server.calls), 2)
            rag.prepare_cases("题目语义 boundary", alternate_queries=("<= 等距比较 boundary",))
            self.assertEqual(len(server.calls), 2)
            self.assertEqual(rag.summary()["case_query_count"], 2)

    def test_shared_read_cache_reuses_query_across_sessions(self):
        with _Server(native_response) as server:
            first = RagflowRAG(self.settings(server.url))
            second = RagflowRAG(self.settings(server.url))
            first.prepare_cases("边界")
            second.prepare_cases("边界")
            self.assertEqual(len(server.calls), 1)
            self.assertEqual(first.summary()["retrieval_stats"]["cache_misses_by_role"], {"cases": 1})
            self.assertEqual(second.summary()["retrieval_stats"]["cache_hits_by_role"], {"cases": 1})

    def test_shared_read_cache_is_disabled_when_ttl_is_zero(self):
        with _Server(native_response) as server:
            settings = replace(self.settings(server.url), ragflow_cache_ttl_s=0)
            first = RagflowRAG(settings)
            second = RagflowRAG(settings)
            first.prepare_cases("边界")
            second.prepare_cases("边界")
            self.assertEqual(len(server.calls), 2)

    def test_shared_read_cache_normalizes_query_whitespace(self):
        with _Server(native_response) as server:
            first = RagflowRAG(self.settings(server.url))
            second = RagflowRAG(self.settings(server.url))
            first.retrieve("  boundary   query  ", top_k=4)
            second.retrieve("boundary query", top_k=4)
            self.assertEqual(len(server.calls), 1)

    def test_shared_read_cache_keeps_code_query_case_distinct(self):
        with _Server(native_response) as server:
            first = RagflowRAG(self.settings(server.url))
            second = RagflowRAG(self.settings(server.url))
            first.retrieve("UserID", top_k=4)
            second.retrieve("userId", top_k=4)
            self.assertEqual(len(server.calls), 2)

    def test_empty_results_are_not_cached(self):
        def empty_response(method, path, body):
            return 200, {"code": 0, "data": {"chunks": []}}

        with _Server(empty_response) as server:
            first = RagflowRAG(self.settings(server.url))
            second = RagflowRAG(self.settings(server.url))
            self.assertEqual(first.retrieve("没有命中", top_k=4), [])
            self.assertEqual(second.retrieve("没有命中", top_k=4), [])
            self.assertEqual(len(server.calls), 2)
            self.assertEqual(first.summary()["retrieval_stats"]["empty_results_not_cached"], 1)

    def test_cross_document_duplicate_references_keep_highest_score(self):
        duplicate = "闆峰瀷: R02 杈圭晫鏉′欢缂哄け\n绌鸿緭鍏ュ拰瓒婄晫鏃跺簲妫€鏌ヨ涓恒€?"
        unique = "闆峰瀷: R02 杈圭晫鏉′欢缂哄け\n瓒呭嚭鏈€澶у€兼椂搴旇繑鍥炴湁鏁堢粨鏋滐紒"

        def responder(method, path, body):
            return 200, {"code": 0, "data": {"chunks": [
                {"id": "chunk-a", "document_id": "document-a", "dataset_id": "dataset-test",
                 "content": duplicate, "similarity": 0.80},
                {"id": "chunk-b", "document_id": "document-b", "dataset_id": "dataset-test",
                 "content": duplicate, "similarity": 0.90},
                {"id": "chunk-c", "document_id": "document-c", "dataset_id": "dataset-test",
                 "content": unique, "similarity": 0.70},
            ]}}

        with _Server(responder) as server:
            rag = RagflowRAG(self.settings(server.url))
            selected = rag.prepare_cases("R02 杈圭晫 boundary")
            self.assertEqual(len(selected), 2)
            self.assertEqual(rag._origins[selected[0]]["document_id"], "document-b")
            quality = rag.summary()["quality_stats"]
            self.assertEqual(quality["duplicate_references"], 1)
            self.assertEqual(quality["cross_document_duplicates"], 1)

    def test_agent_reference_usage_is_counted_without_storing_text(self):
        rag = RagflowRAG(self.settings("http://localhost"))
        rag.record_agent_reference_usage("adversary", ["[ev_a] abc", "[ev_b] 中文"])
        quality = rag.summary()["quality_stats"]
        self.assertEqual(quality["agent_reference_count"], 2)
        self.assertEqual(quality["agent_reference_chars"], len("[ev_a] abc") + len("[ev_b] 中文"))
        self.assertEqual(quality["agent_reference_chars_by_agent"]["adversary"], quality["agent_reference_chars"])

    def test_auxiliary_corpora_are_separate_and_keep_their_roles(self):
        settings = replace(
            self.settings("http://localhost"),
            ragflow_pattern_dataset_id="patterns-test",
            ragflow_negative_dataset_id="negative-test",
        )

        def responder(method, path, body):
            if method != "POST" or path != "/api/v1/retrieval":
                return 404, {}
            dataset_id = body["dataset_ids"][0]
            if dataset_id == "dataset-test":
                text = CASE_TEXT
            elif dataset_id == "patterns-test":
                text = "# 雷型 R02 · 边界条件缺失\n空输入和越界时应检查行为。"
            else:
                text = "类型: 无雷/干扰项（正确代码） | 对应雷型: R02\n正确实现保留空输入约定。"
            return 200, {"code": 0, "data": {"chunks": [{
                "id": "chunk-" + dataset_id,
                "document_id": "document-" + dataset_id,
                "dataset_id": dataset_id,
                "content": text,
                "similarity": 0.8,
            }]}}

        with _Server(responder) as server:
            rag = RagflowRAG(replace(settings, ragflow_base_url=server.url))
            case_ids = rag.prepare_cases("R02 边界条件空输入")
            self.assertEqual(len(case_ids), 1)
            self.assertEqual(server.calls[0]["body"]["dataset_ids"], ["dataset-test"])

            references = rag.prepare_auxiliary(
                "R02 边界条件空输入", expected_code="R02"
            )
            self.assertEqual(len(references["patterns"]), 1)
            self.assertEqual(len(references["negative_code"]), 1)
            self.assertEqual(
                [call["body"]["dataset_ids"] for call in server.calls],
                [["dataset-test"], ["patterns-test"], ["negative-test"]],
            )
            self.assertIn("雷型 R02", rag.fetch(references["patterns"][0]).quote)
            self.assertIn("无雷/干扰项", rag.fetch(references["negative_code"][0]).quote)
            rag.seal()
            self.assertEqual(
                rag._origins[references["patterns"][0]]["role"], "patterns"
            )
            self.assertEqual(
                rag._origins[references["negative_code"][0]]["role"], "negative_code"
            )
            summary = rag.summary()["retrieval_stats"]
            self.assertEqual(summary["requests_by_role"], {
                "cases": 1, "patterns": 1, "negative_code": 1,
            })
            self.assertEqual(summary["selected_by_role"], {
                "cases": 1, "patterns": 1, "negative_code": 1,
            })

    def test_compact_reference_keeps_review_signals(self):
        text = "# 雷型 R02 · 边界条件缺失\n" + ("无关代码片段 " * 300) + "判级依据：空输入触发越界，L2 定位级。"
        compacted = compact_reference(text, 220)
        self.assertLessEqual(len(compacted), 220)
        self.assertIn("R02", compacted)
        self.assertTrue(any(word in compacted for word in ("判级", "空输入", "L2")))

    def test_seal_persists_provenance_and_never_retrieves_again(self):
        with _Server(native_response) as server:
            rag = RagflowRAG(self.settings(server.url))
            rag.index("doc_a", ALPHA, language="python")
            case = rag.prepare_cases("边界")
            rag.seal()
            rag.seal()
            with self.assertRaises(IndexSealed):
                rag.retrieve("边界")
            with self.assertRaises(IndexSealed):
                rag.index("doc_a", BETA, language="python")
            self.assertEqual(rag.fetch(case[0]).quote, CASE_TEXT)
            self.assertEqual(len(server.calls), 1)
            files = list(Path(self.directory.name).glob("*.json"))
            self.assertEqual(len(files), 1)
            saved = files[0].read_text(encoding="utf-8")
            self.assertNotIn("secret-test-key", saved)
            snapshot = json.loads(saved)
            self.assertTrue(snapshot["source_evidence"])
            self.assertEqual(snapshot["provenance"][case[0]]["chunk_id"], "chunk-1")
            span = snapshot["case_evidence"][case[0]]
            self.assertEqual(span["quote"][span["char_start"]:span["char_end"]], CASE_TEXT)

    def test_business_errors_cross_dataset_and_empty_hits_fail_closed(self):
        bad_chunk = {"id": "x", "document_id": "y", "dataset_id": "other",
                     "content": "不可混入其他库"}
        for response in ({"code": 100, "message": "error"},
                         {"code": 0, "data": {"chunks": [bad_chunk]}},
                         {"code": 0, "data": {"chunks": []}}):
            with self.subTest(response=response):
                with _Server(lambda *args: (200, response)) as server:
                    rag = RagflowRAG(self.settings(server.url))
                    with self.assertRaises(RAGError):
                        rag.prepare_cases("边界")
                    self.assertTrue(rag.summary()["last_error"])
                    self.assertFalse(rag.summary()["degraded"])

    def test_snapshot_write_failure_is_a_domain_error(self):
        occupied = Path(self.directory.name) / "file"
        occupied.touch()
        rag = RagflowRAG(replace(self.settings("http://localhost"),
                                 case_snapshot_dir=str(occupied)))
        with self.assertRaises(RAGError):
            rag.seal()
        self.assertFalse(rag.sealed)

    def test_two_sessions_share_cases_without_sharing_a_seal(self):
        prompts = []
        original = MockLLM.complete

        def record(client, messages, **kwargs):
            prompts.append("\n".join(message["content"] for message in messages))
            return original(client, messages, **kwargs)

        pattern_text = "# 雷型 R02 · 边界条件缺失\n空输入和越界边界应单独检查。"
        negative_text = "类型: 无雷/干扰项（正确代码） | 对应雷型: R02\n正确实现满足题目边界约定。"

        def responder(method, path, body):
            if method != "POST" or path != "/api/v1/retrieval":
                return 404, {}
            dataset_id = body["dataset_ids"][0]
            text = {
                "dataset-test": CASE_TEXT,
                "patterns-test": pattern_text,
                "negative-test": negative_text,
            }[dataset_id]
            return 200, {"code": 0, "data": {"chunks": [{
                "id": "chunk-" + dataset_id,
                "document_id": "document-" + dataset_id,
                "dataset_id": dataset_id,
                "content": text,
                "similarity": 0.8,
            }]}}

        with _Server(responder) as server, patch.object(MockLLM, "complete", record):
            settings = replace(
                self.settings(server.url),
                ragflow_pattern_dataset_id="patterns-test",
                ragflow_negative_dataset_id="negative-test",
            )
            store = SessionStore(settings)
            first = store.open()
            second = store.open()
            self.assertNotEqual(first["session_id"], second["session_id"])
            self.assertNotIn(CASE_TEXT, json.dumps(first, ensure_ascii=False))
            self.assertNotIn(pattern_text, json.dumps(first, ensure_ascii=False))
            self.assertNotIn(negative_text, json.dumps(first, ensure_ascii=False))
            anchors = store.anchors(first["session_id"])
            self.assertNotIn("pattern_evidence_ids", json.dumps(anchors))
            self.assertNotIn("negative_evidence_ids", json.dumps(anchors))
            case_id = anchors[0]["case_evidence_ids"][0]
            self.assertNotIn(case_id, json.dumps(first))
            source = first["items"][0]["evidence"][0]["evidence_id"]
            with self.assertRaises(EvidenceForbidden):
                store.evidence(source, session_id=first["session_id"])
            with self.assertRaises(CitationOutsideAnchor):
                store.submit(first["session_id"], "item-1", "边界条件", cited=[case_id])
            requests_before = len(server.calls)
            store.submit(first["session_id"], "item-1", "比较条件影响等距候选。", cited=[source])
            store.settle(first["session_id"])
            store.settle(second["session_id"])
            self.assertEqual(len(server.calls), requests_before)
            self.assertTrue(store.evidence(source, session_id=first["session_id"])["quote"])
            with self.assertRaises(EvidenceForbidden):
                store.evidence(case_id, session_id=first["session_id"])
            for task in ("adversary", "judge_escalation"):
                self.assertTrue(any("TASK=" + task in p and CASE_TEXT in p for p in prompts))
            compact_pattern = compact_reference(pattern_text, 520)
            compact_negative = compact_reference(negative_text, 560)
            self.assertTrue(any("TASK=adversary" in p and compact_pattern in p for p in prompts))
            self.assertTrue(any("TASK=judge_escalation" in p and compact_pattern in p for p in prompts))
            self.assertTrue(any("TASK=judge_escalation" in p and compact_negative in p for p in prompts))
            self.assertFalse(any("TASK=adversary" in p and negative_text in p for p in prompts))
            self.assertFalse(any("TASK=judge_decision" in p and negative_text in p for p in prompts))
            self.assertTrue(all(CASE_TEXT not in p for p in prompts if "TASK=judge_decision" in p))
            self.assertEqual(len(list(Path(self.directory.name).glob("*.json"))), 2)
            quality = store._entries[first["session_id"]].retriever.summary()["quality_stats"]
            self.assertGreater(quality["agent_reference_count_by_agent"]["adversary"], 0)
            self.assertGreater(quality["agent_reference_chars_by_agent"]["adversary"], 0)

    def test_unavailable_ragflow_does_not_create_a_fake_session(self):
        store = SessionStore(self.settings("http://127.0.0.1:1"))
        with self.assertRaises(UpstreamError):
            store.open()
        self.assertEqual(store.count(), 0)

    def test_replacing_source_removes_stale_chunks(self):
        rag = LocalStubRAG()
        rag.index("doc_a", ALPHA + "\n" + BETA, language="python")
        rag.index("doc_a", ALPHA, language="python")
        chunks = rag.retrieve("beta", doc_id="doc_a")
        self.assertEqual(len(chunks), 1)
        self.assertNotIn("def beta", chunks[0].text)

    def test_case_candidates_are_reranked_by_explicit_defect_type(self):
        candidates = [
            RetrievedChunk("ev_init", "d1", "1", "雷型: R04 状态与初始化错误，变量未初始化", 0, 25, 0.90),
            RetrievedChunk("ev_tie", "d2", "2", "雷型: R03 逻辑错误，等距候选比较条件导致返回值不稳定", 0, 30, 0.72),
            RetrievedChunk("ev_boundary", "d3", "3", "雷型: R02 边界条件缺失，空输入越界", 0, 22, 0.88),
        ]
        selected = rerank_cases("等距候选逻辑 logic python", candidates, 2)
        self.assertEqual(selected[0].evidence_id, "ev_tie")
        self.assertEqual(len(selected), 2)

        # 通用正文词“状态”不应把 R04 初始化判例冒充逻辑型。
        init = RetrievedChunk("ev_r04", "d4", "4", "雷型: R04 状态与初始化错误 | 判例：学生主张无雷", 0, 28, 0.99)
        valid = RetrievedChunk("ev_r06", "d5", "5", "雷型: R06 逻辑错误 | 等距候选应保持遍历稳定", 0, 28, 0.70)
        stats = {}
        rerank_cases("等距候选 logic", [init, valid], 1, stats=stats)
        self.assertEqual(stats["type_matches"], 1)
        self.assertEqual(stats["mismatch_filtered"], 1)

    def test_rerank_deduplicates_and_reports_matches(self):
        chunk = RetrievedChunk("ev_a", "d", "1", "雷型: R02 边界条件缺失 空输入", 0, 20, 0.5)
        stats = {}
        selected = rerank_cases("空输入 boundary", [chunk, chunk], 3, stats=stats)
        self.assertEqual([c.evidence_id for c in selected], ["ev_a"])
        self.assertEqual(stats["candidates"], 2)
        self.assertEqual(stats["selected"], 1)
        self.assertGreaterEqual(stats["type_matches"], 1)


if __name__ == "__main__":
    unittest.main()
