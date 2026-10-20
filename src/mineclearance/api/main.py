"""FastAPI 薄壳：把 JSON 翻成 store 的调用，再翻回来。

跑法（仓库根目录，且已 pip install -r requirements.txt）：
    uvicorn mineclearance.api.main:app --reload

三条边界，写在这里免得以后有人往里加业务逻辑：
    1  这里没有判级、没有引用核验、没有预算计算，全在 core。壳里出现 if 判断分数，就是错的。
    2  这里不发任何模型调用。一次 HTTP 请求最多引发主链里一次已记账的调用。
    3  异常一律走 StoreError → 对应状态码，不把上游的 500 原样吐给前端。

SSE 用来做「对抗轮次边生成边显示」。没有 SSE 也能用：同一个 URL 不带
Accept: text/event-stream 就是普通 JSON 响应。流式是体验，不是依赖。
"""

from __future__ import annotations

import json
import os
import queue
import threading
from typing import Dict, List, Optional

try:
    from fastapi import FastAPI, Request
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import JSONResponse, Response, StreamingResponse
    from pydantic import BaseModel, Field
except ModuleNotFoundError as exc:  # pragma: no cover - 只有没装依赖时才会走到
    raise RuntimeError(
        "Web 层需要额外依赖：pip install -r requirements.txt。"
        "核心链路（scripts/smoke.py 与 unittest）只依赖标准库，不受影响。"
    ) from exc

from ..budget import STAGE_LIMITS
from ..config import Settings
from ..schemas import SCHEMA_VERSION, DefectType, ItemSpec, Level
from .store import SessionStore, StoreError

DEFAULT_CORS = ("http://localhost:5173", "http://127.0.0.1:5173")


# ---- 请求体 ----


class ItemSpecIn(BaseModel):
    item_id: str = Field(..., min_length=1)
    topic: str = Field(..., min_length=1)
    language: str = "python"
    defect_type: str = DefectType.LOGIC.value
    expected_level: str = Level.L2.value

    def to_spec(self) -> ItemSpec:
        return ItemSpec(
            item_id=self.item_id,
            topic=self.topic,
            language=self.language,
            defect_type=DefectType(self.defect_type),
            expected_level=Level(self.expected_level),
        )


class OpenIn(BaseModel):
    """不传 specs 就用内置的出题单，现场演示不必先准备题库。"""

    specs: Optional[List[ItemSpecIn]] = None


class AnswerIn(BaseModel):
    item_id: str = Field(..., min_length=1)
    text: str = Field(..., min_length=1)
    cited_evidence_ids: List[str] = Field(default_factory=list)
    proposed_fix: str = ""


class RetrieveIn(BaseModel):
    """预留的检索代理入参。前端只认这个，不认 RAG 后端地址。"""

    query: str = Field(..., min_length=1)
    top_k: int = Field(5, ge=1, le=50)
    doc_id: Optional[str] = None
    session_id: Optional[str] = None


def create_app(settings: Optional[Settings] = None, store: Optional[SessionStore] = None) -> FastAPI:
    settings = settings or Settings.from_env()
    session_store = store or SessionStore(settings)

    app = FastAPI(
        title="排雷兵 · Mine-clearance",
        version=SCHEMA_VERSION,
        description="学会拆穿 AI 写的代码。核心链路在 core，这里只有 HTTP 适配。",
    )
    app.state.store = session_store
    app.state.settings = settings
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins(),
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=["Content-Type"],
    )

    # ---- 领域错误 → 状态码 ----

    @app.exception_handler(StoreError)
    def _on_store_error(_: Request, exc: StoreError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status, content={"error": type(exc).__name__, "detail": str(exc)}
        )

    @app.exception_handler(ValueError)
    def _on_value_error(_: Request, exc: ValueError) -> JSONResponse:
        return JSONResponse(status_code=422, content={"error": "InvalidInput", "detail": str(exc)})

    # ---- 系统 ----

    @app.get("/v1/health", tags=["system"])
    def health() -> dict:
        return {
            "status": "ok",
            "schema_version": SCHEMA_VERSION,
            "llm_provider": settings.llm_provider,
            # false = 只配了一家厂商，对抗与升级裁判同源。判级复核因此不可信，
            # 这一行是给「你们怎么保证不同源」这个问题的现场答案。
            "vendor_isolated": session_store.vendor_isolated(),
            "calls_per_session_cap": settings.max_calls_per_session,
            "cost_budget_cny": settings.cost_budget_cny,
            "stage_limits": dict(STAGE_LIMITS),
            "probe": type(session_store.probe).__name__ if session_store.probe else "none",
            "rag": session_store.rag_summary(),
            "sessions": session_store.count(),
        }

    # ---- 三段主链 ----

    @app.post("/v1/sessions", status_code=201, tags=["session"])
    def open_session(payload: Optional[OpenIn] = None) -> dict:
        specs = [spec.to_spec() for spec in payload.specs] if payload and payload.specs else None
        return session_store.open(specs)

    @app.get("/v1/sessions/{session_id}", tags=["session"])
    def session_state(session_id: str) -> dict:
        return session_store.state(session_id)

    @app.delete("/v1/sessions/{session_id}", status_code=204, tags=["session"])
    def close_session(session_id: str) -> Response:
        session_store.close(session_id)
        return Response(status_code=204)

    @app.post("/v1/sessions/{session_id}/submit", tags=["session"])
    def submit_answer(session_id: str, payload: AnswerIn, request: Request):
        kwargs = dict(
            cited=payload.cited_evidence_ids,
            proposed_fix=payload.proposed_fix,
        )
        if _wants_stream(request):
            return StreamingResponse(
                _stream(session_store, session_id, payload.item_id, payload.text, kwargs),
                media_type="text/event-stream",
                headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
            )
        return session_store.submit(session_id, payload.item_id, payload.text, **kwargs)

    @app.post("/v1/sessions/{session_id}/settle", tags=["session"])
    def settle(session_id: str) -> dict:
        return session_store.settle(session_id)

    # ---- 预留的 RAG 代理（读方向；写索引不开放，见 store 里的说明）----

    @app.post("/v1/retrieve", tags=["rag"])
    def retrieve(payload: RetrieveIn) -> dict:
        return session_store.retrieve(
            payload.query,
            top_k=payload.top_k,
            doc_id=payload.doc_id,
            session_id=payload.session_id,
        )

    @app.get("/v1/evidence/{evidence_id}", tags=["rag"])
    def evidence(evidence_id: str, session_id: Optional[str] = None) -> dict:
        return session_store.evidence(evidence_id, session_id=session_id)

    return app


# ---- SSE ----


def _wants_stream(request: Request) -> bool:
    return "text/event-stream" in (request.headers.get("accept") or "")


def _stream(store: SessionStore, session_id: str, item_id: str, text: str, kwargs: Dict):
    """同步生成器：Starlette 会把它放到线程池里跑。

    模型调用在另一个线程里发生，token 通过队列回到这里。
    这样写而不是用 asyncio，是因为 Router 是同步接口，硬套 async 只会多一层坑。
    """
    channel: "queue.Queue" = queue.Queue()

    def on_token(token: str) -> None:
        channel.put(("token", token))

    def work() -> None:
        try:
            result = store.submit(session_id, item_id, text, on_token=on_token, **kwargs)
            channel.put(("result", result))
        except StoreError as exc:
            channel.put(("error", {"error": type(exc).__name__, "detail": str(exc), "status": exc.status}))
        except Exception as exc:  # 兜底：流已经开了，不能只留一条断掉的连接
            channel.put(("error", {"error": type(exc).__name__, "detail": str(exc), "status": 500}))
        finally:
            channel.put(None)

    threading.Thread(target=work, name="mc-submit", daemon=True).start()

    while True:
        event = channel.get()
        if event is None:
            break
        kind, value = event
        yield "event: %s\ndata: %s\n\n" % (kind, json.dumps(value, ensure_ascii=False))
    yield "event: done\ndata: {}\n\n"


def _cors_origins() -> List[str]:
    configured = os.getenv("MC_CORS_ORIGINS", "").strip()
    if not configured:
        return list(DEFAULT_CORS)
    return [origin.strip() for origin in configured.split(",") if origin.strip()]


app = create_app()
