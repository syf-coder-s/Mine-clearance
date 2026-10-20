"""检索层：切分、证据 id、封印、doc_id 作用域，以及 HTTP 契约。

HTTP 部分用一个本机临时服务做，不联网、不要密钥，但它真的走了一遍
urllib → 请求体 → 返回体 → 契约校验，所以 docs/rag-api.md 写的东西是被测过的。
"""

from __future__ import annotations

import json
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mineclearance.rag import (  # noqa: E402
    HttpRAG,
    IndexSealed,
    LocalStubRAG,
    RAGError,
    ResilientRAG,
    SealedView,
    make_evidence_id,
    rank_and_cut,
)
from mineclearance.rag import chunking  # noqa: E402

ALPHA = "def alpha(values):\n    return values[0]\n"
BETA = "def beta(values):\n    return values[-1]\n"


class ChunkingTest(unittest.TestCase):
    def test_code_is_cut_by_function(self):
        text = "def a(x):\n    return x\n\ndef b(x):\n    return x + 1\n"
        spans = chunking.split(text, "python")
        self.assertEqual(len(spans), 2)
        for start, end in spans:
            piece = text[start:end]
            self.assertTrue(piece.startswith("def "), piece)
            self.assertIn("return", piece)

    def test_spans_point_at_original_text(self):
        text = "\n\n## 一\n正文一\n\n## 二\n正文二\n"
        for start, end in chunking.split(text, "markdown"):
            self.assertEqual(text[start:end], text[start:end].strip())
            self.assertTrue(0 <= start < end <= len(text))

    def test_empty_document(self):
        self.assertEqual(chunking.split("   \n\n", "python"), [])


class EvidenceIdTest(unittest.TestCase):
    def test_id_depends_only_on_position(self):
        first = make_evidence_id("doc_a", 0, 12)
        self.assertEqual(first, make_evidence_id("doc_a", 0, 12))
        self.assertNotEqual(first, make_evidence_id("doc_a", 0, 13))
        self.assertNotEqual(first, make_evidence_id("doc_b", 0, 12))
        self.assertTrue(first.startswith("ev_"))

    def test_rerun_of_the_same_document_yields_the_same_ids(self):
        ids = []
        for _ in range(2):
            stub = LocalStubRAG()
            stub.index("doc_a", ALPHA, language="python")
            ids.append([c.evidence_id for c in stub.retrieve("alpha", top_k=5)])
        self.assertEqual(ids[0], ids[1])


class StubScopeTest(unittest.TestCase):
    def setUp(self) -> None:
        self.stub = LocalStubRAG()
        self.stub.index("doc_a", ALPHA, language="python")
        self.stub.index("doc_b", BETA, language="python")

    def test_doc_scope_keeps_evidence_inside_one_document(self):
        # 这一条曾经真的错过：不限 doc_id 时，item-1 的证据指向了 item-2 的代码。
        found = self.stub.retrieve("alpha beta", top_k=10, doc_id="doc_a")
        self.assertTrue(found)
        self.assertTrue(all(c.doc_id == "doc_a" for c in found))

    def test_unscoped_retrieval_spans_all_documents(self):
        found = self.stub.retrieve("", top_k=10)
        self.assertEqual({c.doc_id for c in found}, {"doc_a", "doc_b"})

    def test_empty_query_falls_back_to_position_not_fake_relevance(self):
        found = self.stub.retrieve("完全无关的中文查询", top_k=2, doc_id="doc_a")
        self.assertTrue(found)
        self.assertEqual(found[0].score, 0.0)  # 兜底不许伪装成命中

    def test_fetch_returns_the_original_slice(self):
        chunk = self.stub.retrieve("alpha", top_k=1, doc_id="doc_a")[0]
        span = self.stub.fetch(chunk.evidence_id)
        self.assertEqual(span.quote, ALPHA[span.char_start : span.char_end])
        self.assertEqual(len(span.quote), span.char_end - span.char_start)

    def test_unknown_evidence_is_an_error_not_none(self):
        with self.assertRaises(RAGError):
            self.stub.fetch("ev_nope")

    def test_seal_blocks_reindexing_and_researching_but_allows_fetch(self):
        chunk = self.stub.retrieve("alpha", top_k=1, doc_id="doc_a")[0]
        self.stub.seal()
        self.assertTrue(self.stub.sealed)
        with self.assertRaises(IndexSealed):
            self.stub.retrieve("alpha", top_k=1, doc_id="doc_a")
        with self.assertRaises(IndexSealed):
            self.stub.index("doc_c", "def c():\n    pass\n", language="python")
        self.assertEqual(self.stub.fetch(chunk.evidence_id).doc_id, "doc_a")

    def test_sealed_view_has_no_retrieve(self):
        # 「再查一次」在类型层面就写不出来，只有按 id 取。
        stub = LocalStubRAG()
        stub.index("doc_a", ALPHA, language="python")
        stub.seal()
        view = SealedView(stub)
        self.assertFalse(hasattr(view, "retrieve"))
        chunk_id = stub.chunk_ids("doc_a")[0]
        self.assertEqual(len(view.fetch_many([chunk_id, "ev_missing"])), 1)

    def test_rank_and_cut_sorts_by_score_then_position(self):
        from mineclearance.rag import RetrievedChunk

        def chunk(start: int, score: float) -> RetrievedChunk:
            return RetrievedChunk(
                evidence_id="ev_%d" % start,
                doc_id="doc_a",
                chunk_id="c",
                text="t",
                char_start=start,
                char_end=start + 1,
                score=score,
            )

        ranked = rank_and_cut([chunk(20, 0.2), chunk(10, 0.5), chunk(30, 0.5)], 2)
        self.assertEqual([c.char_start for c in ranked], [10, 30])
        self.assertEqual(rank_and_cut([chunk(0, 0.1)], 3, min_score=0.2), [])


# ---- HTTP 契约 ----


class _Handler(BaseHTTPRequestHandler):
    def _dispatch(self) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length).decode("utf-8") if length else ""
        body = json.loads(raw) if raw.strip() else None
        self.server.calls.append(
            {
                "method": self.command,
                "path": self.path,
                "body": body,
                "auth": self.headers.get("Authorization"),
            }
        )
        status, payload = self.server.responder(self.command, self.path, body)
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    do_GET = _dispatch
    do_POST = _dispatch

    def log_message(self, *args) -> None:  # 测试输出别被打日志刷掉
        return


class _Server:
    def __init__(self, responder) -> None:
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        self.httpd.daemon_threads = True
        self.httpd.responder = responder
        self.httpd.calls = []
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)

    def __enter__(self):
        self.thread.start()
        host, port = self.httpd.server_address[:2]
        self.url = "http://%s:%d" % (host, port)
        self.calls = self.httpd.calls
        return self

    def __exit__(self, *exc) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(timeout=2)


def happy_responder(method, path, body):
    if path == "/v1/index":
        return 200, {"chunks": 2}
    if path == "/v1/retrieve":
        return 200, {
            "items": [
                {
                    "evidence_id": "ev_1",
                    "doc_id": "doc_a",
                    "chunk_id": "doc_a#0-1",
                    "text": "x",
                    "char_start": 0,
                    "char_end": 1,
                    "score": 0.5,
                }
            ]
        }
    if path.startswith("/v1/evidence/"):
        return 200, {
            "evidence_id": "ev_1",
            "doc_id": "doc_a",
            "chunk_id": "doc_a#0-1",
            "char_start": 0,
            "char_end": 1,
            "quote": "x",
        }
    if path == "/v1/seal":
        return 200, {}
    return 404, {"detail": "not found"}


class HttpContractTest(unittest.TestCase):
    def test_full_round_trip(self):
        with _Server(happy_responder) as server:
            client = HttpRAG(server.url, "sk-test", timeout_s=2.0, retries=0)

            self.assertEqual(client.index("doc_a", ALPHA, language="python"), 2)
            chunks = client.retrieve("alpha", top_k=3, doc_id="doc_a")
            self.assertEqual(chunks[0].evidence_id, "ev_1")
            span = client.fetch("ev_1")
            self.assertEqual(span.quote, "x")

            client.seal()
            self.assertTrue(client.sealed)
            self.assertEqual(server.calls[0]["auth"], "Bearer sk-test")
            self.assertEqual(server.calls[1]["path"], "/v1/retrieve")
            self.assertEqual(server.calls[1]["body"], {"query": "alpha", "top_k": 3, "doc_id": "doc_a"})

            sent = len(server.calls)
            with self.assertRaises(IndexSealed):
                client.retrieve("再来一次", top_k=3)
            self.assertEqual(len(server.calls), sent, "封印后不该再发请求")

    def test_doc_id_is_optional_on_the_wire(self):
        with _Server(happy_responder) as server:
            client = HttpRAG(server.url, retries=0)
            client.retrieve("alpha", top_k=3)
            body = server.calls[0]["body"]
            self.assertNotIn("doc_id", body)  # 不带就是不限文档，契约里没这个字段
            self.assertIsNone(server.calls[0]["auth"])  # 没配密钥就不发 Authorization

    def test_malformed_items_break_loudly(self):
        def responder(method, path, body):
            return 200, {"items": [{"evidence_id": "ev_1", "doc_id": "doc_a", "char_start": 0, "char_end": 1}]}

        with _Server(responder) as server:
            with self.assertRaises(RAGError):
                HttpRAG(server.url, retries=0).retrieve("alpha", top_k=1)

    def test_inconsistent_evidence_span_is_rejected(self):
        # quote 长度与区间对不上，等于引用不可核验，必须当场失败。
        def responder(method, path, body):
            return 200, {"evidence_id": "ev_1", "doc_id": "doc_a", "char_start": 0, "char_end": 5, "quote": "x"}

        with _Server(responder) as server:
            with self.assertRaises(RAGError):
                HttpRAG(server.url, retries=0).fetch("ev_1")

    def test_server_error_is_wrapped(self):
        def responder(method, path, body):
            return 500, {"detail": "boom"}

        with _Server(responder) as server:
            with self.assertRaises(RAGError) as caught:
                HttpRAG(server.url, retries=0).index("doc_a", ALPHA)
            self.assertIn("500", str(caught.exception))


class _BrokenRAG:
    """索引能写、检索会炸。用来验证降级发生在「第一次失败」而不是每次失败。"""

    def __init__(self) -> None:
        self.sealed = False
        self.indexed = []

    def index(self, doc_id, text, *, language="text"):
        self.indexed.append(doc_id)
        return len(text)

    def retrieve(self, query, *, top_k=10, doc_id=None):
        raise RAGError("backend down")

    def fetch(self, evidence_id):
        raise RAGError("backend down")

    def seal(self):
        self.sealed = True


class ResilienceTest(unittest.TestCase):
    def test_degrades_and_replays_what_was_already_indexed(self):
        primary = _BrokenRAG()
        rag = ResilientRAG(primary)
        self.assertEqual(rag.index("doc_a", ALPHA, language="python"), len(ALPHA))
        self.assertFalse(rag.degraded)

        chunks = rag.retrieve("alpha", top_k=3, doc_id="doc_a")
        self.assertTrue(rag.degraded)
        self.assertTrue(chunks, "降级后应能读到降级前写入的文档")
        self.assertEqual(chunks[0].doc_id, "doc_a")
        self.assertIn("backend down", rag.summary()["degrade_reason"])

    def test_unreachable_backend_does_not_crash_the_session(self):
        client = HttpRAG("http://127.0.0.1:1", timeout_s=0.2, retries=0)
        rag = ResilientRAG(client)
        rag.index("doc_a", ALPHA, language="python")
        self.assertTrue(rag.degraded)
        self.assertTrue(rag.retrieve("alpha", top_k=3, doc_id="doc_a"))
        rag.seal()
        self.assertTrue(rag.sealed)


if __name__ == "__main__":
    unittest.main()
