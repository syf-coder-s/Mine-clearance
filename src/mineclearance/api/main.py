"""FastAPI 薄壳：把 JSON 翻成 store 的调用，再翻回来。

跑法（仓库根目录，且已 pip install -r requirements.txt）：
    $env:PYTHONPATH = "src"
    python -m uvicorn mineclearance.api.main:app --reload --port 8010

三条边界，写在这里免得以后有人往里加业务逻辑：
    1  这里没有判级、没有引用核验、没有预算计算，全在 core。壳里出现 if 判断分数，就是错的。
    2  这里不发任何模型调用。一次 HTTP 请求最多引发主链里一次已记账的调用。
    3  异常一律走 StoreError → 对应状态码，不把上游的 500 原样吐给前端。

SSE 用来做「对抗轮次边生成边显示」。没有 SSE 也能用：同一个 URL 不带
Accept: text/event-stream 就是普通 JSON 响应。流式是体验，不是依赖。
"""

from __future__ import annotations

import hmac
import json
import os
import queue
import threading
from typing import Dict, List, Optional

try:
    from fastapi import FastAPI, Request
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response, StreamingResponse
    from pydantic import BaseModel, Field
except ModuleNotFoundError as exc:  # pragma: no cover - 只有没装依赖时才会走到
    raise RuntimeError(
        "Web 层需要额外依赖：pip install -r requirements.txt。"
        "核心链路（scripts/smoke.py 与 unittest）只依赖标准库，不受影响。"
    ) from exc

from ..budget import STAGE_LIMITS
from ..config import Settings
from ..schemas import SCHEMA_VERSION, DefectType, ItemSpec, Level
from ..upstream import (
    AnchorForbidden,
    Upstream,
    UpstreamFault,
    anchor_view,
    build_upstream,
)
from .static_serve import mount_frontend, resolve_dist
from .store import SessionStore, StoreError

DEFAULT_CORS = ("http://localhost:5173", "http://127.0.0.1:5173",
                "http://localhost:5174", "http://127.0.0.1:5174")


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


# ---- 裁决层入参（预留给后端对接）----
#
# 这几个模型的两个共同点，都是故意的：
#   1  stage 写成 Optional。缺字段要 409（状态必须由裁决方决定），
#      而不是 pydantic 默认的 422 —— 422 是「参数格式不对」，语义不一样。
#   2  不在这里做业务校验（比如「结算后还能不能对抗」），一律交给 upstream。


class StageIn(BaseModel):
    session_id: str = Field(..., min_length=1)
    stage: Optional[str] = None


class ReserveIn(BaseModel):
    session_id: str = Field(..., min_length=1)
    stage: Optional[str] = None
    units: int = Field(1, ge=1, le=3)


class CommitIn(BaseModel):
    reservation_id: str = Field(..., min_length=1)
    cost_cny: float = Field(0.0, ge=0.0)


class VoidIn(BaseModel):
    reservation_id: str = Field(..., min_length=1)


class VerifyIn(BaseModel):
    session_id: str = Field(..., min_length=1)
    evidence_ids: List[str] = Field(default_factory=list)


def create_app(
    settings: Optional[Settings] = None,
    store: Optional[SessionStore] = None,
    upstream: Optional[Upstream] = None,
) -> FastAPI:
    settings = settings or Settings.from_env()
    session_store = store or SessionStore(settings)
    decider = upstream or build_upstream(settings)

    app = FastAPI(
        title="排雷兵 · Mine-clearance",
        version=SCHEMA_VERSION,
        description="学会拆穿 AI 写的代码。核心链路在 core，这里只有 HTTP 适配。",
    )
    app.state.store = session_store
    app.state.settings = settings
    app.state.upstream = decider
    # 同源托管前端：存在 frontend/dist 时由后端直接服务 / 与前端路由（见 static_serve.py）
    frontend_dist = resolve_dist(os.getenv("FRONTEND_DIST_DIR"))
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

    @app.exception_handler(UpstreamFault)
    def _on_upstream_fault(_: Request, exc: UpstreamFault) -> JSONResponse:
        # 409 状态非法 / 403 越权 / 422 越域 / 502 后端连不上，四档都在 exc 上带着。
        return JSONResponse(status_code=exc.status, content={"error": exc.code, "detail": str(exc)})

    # ---- 系统 ----

    @app.get("/", include_in_schema=False)
    def home():
        if frontend_dist is not None:
            return FileResponse(frontend_dist / "index.html")
        return RedirectResponse("/docs")

    @app.get("/v1/health", tags=["system"])
    def health() -> dict:
        return {
            "status": "ok",
            "schema_version": SCHEMA_VERSION,
            "llm_provider": settings.llm_provider,
            "mock_llm": settings.use_mock_llm(),
            "model_routes": session_store.model_routes(),
            "cost_known": False,
            "cost_note": "未配置核实后的单价；cost_cny=0 表示未估价，金额预算尚不能保证；调用次数上限仍有效",
            # false = 只配了一家厂商，对抗与升级裁判同源。判级复核因此不可信，
            # 这一行是给「你们怎么保证不同源」这个问题的现场答案。
            "vendor_isolated": session_store.vendor_isolated(),
            "calls_per_session_cap": settings.max_calls_per_session,
            "cost_budget_cny": settings.cost_budget_cny,
            "stage_limits": dict(STAGE_LIMITS),
            "probe": type(session_store.probe).__name__ if session_store.probe else "none",
            "rag": session_store.rag_summary(),
            # fake = 本地内存裁决，http = 已接到后端。这一项和后端同学联调时先看一眼。
            "upstream": decider.summary(),
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
    def retrieve(payload: RetrieveIn, request: Request) -> dict:
        if settings.rag_provider.lower() == "ragflow" and not payload.session_id:
            _require_internal(settings, request)
        return session_store.retrieve(
            payload.query,
            top_k=payload.top_k,
            doc_id=payload.doc_id,
            session_id=payload.session_id,
        )

    @app.get("/v1/evidence/{evidence_id}", tags=["rag"])
    def evidence(evidence_id: str, request: Request, session_id: Optional[str] = None) -> dict:
        if settings.rag_provider.lower() == "ragflow" and not session_id:
            _require_internal(settings, request)
        return session_store.evidence(evidence_id, session_id=session_id)

    # ---- 裁决层（预留给后端对接）----
    #
    # 现在默认走 FakeUpstream（内存实现），七个端点全都能跑；把 UPSTREAM_BASE_URL
    # 填上就整体切到 HttpUpstream，一行代码不用改。主链**尚未**调用它们——
    # 等后端接上，在 Session.submit / settle 各加一行，接法见 docs/upstream-api.md。
    #
    # 这里只做两件事：把 JSON 递进去，把异常交给上面的 handler。判断一律不在这层写。

    @app.post("/v1/stage", tags=["upstream"])
    def propose_stage(payload: StageIn) -> dict:
        _sync_anchors(session_store, decider, payload.session_id)
        ticket = decider.propose_stage(payload.session_id, payload.stage or "")
        return {
            "session_id": ticket.session_id,
            "stage": ticket.stage,
            "previous": ticket.previous,
            "seq": ticket.seq,
        }

    @app.post("/v1/budget/reserve", tags=["upstream"])
    def reserve_budget(payload: ReserveIn) -> dict:
        _sync_anchors(session_store, decider, payload.session_id)
        return _reservation_view(decider.reserve(payload.session_id, payload.stage or "", payload.units))

    @app.post("/v1/budget/commit", tags=["upstream"])
    def commit_budget(payload: CommitIn) -> dict:
        return _reservation_view(decider.commit(payload.reservation_id, payload.cost_cny))

    @app.post("/v1/budget/void", tags=["upstream"])
    def void_budget(payload: VoidIn) -> dict:
        return _reservation_view(decider.void(payload.reservation_id))

    # 锚点只对内部开放：里面有 trigger / fix 这类答案侧信息，下发即泄露。
    # 令牌留空时一律 403 —— 宁可不给，也不默认敞开。

    @app.get("/v1/anchor/{item_id}", tags=["upstream"])
    def read_anchor(item_id: str, request: Request, session_id: str) -> dict:
        _require_internal(settings, request)
        _sync_anchors(session_store, decider, session_id)
        return anchor_view(decider.anchor(session_id, item_id))

    @app.post("/v1/anchor/{item_id}/verify", tags=["upstream"])
    def verify_reference(item_id: str, payload: VerifyIn, request: Request) -> dict:
        _require_internal(settings, request)
        _sync_anchors(session_store, decider, payload.session_id)
        checked = decider.verify_reference(payload.session_id, item_id, payload.evidence_ids)
        return {"ok": True, "item_id": item_id, "checked": checked}

    # SPA 兜底必须放在所有显式路由之后，避免吞掉 /v1/* 与 /docs。
    if frontend_dist is not None:
        mount_frontend(app, frontend_dist)

    return app


# ---- 裁决层的小工具 ----


def _sync_anchors(store: SessionStore, decider: Upstream, session_id: str) -> None:
    """把这场会话封存的证据集合登记给裁决方。

    登记是幂等的：重复登记必须一字不差，Fake 会拿 409 拦住「中途换判例集合」。
    HTTP 模式下 sync_session 是空实现——锚点由后端在 seal 时自己冻结。
    """
    decider.sync_session(session_id, store.anchors(session_id))


def _require_internal(settings: Settings, request: Request) -> None:
    expected = settings.internal_token
    if not expected:
        raise AnchorForbidden("未配置 MC_INTERNAL_TOKEN：锚点只对内部调用方开放")
    provided = request.headers.get("x-internal-token", "")
    if not hmac.compare_digest(provided, expected):
        raise AnchorForbidden("内部令牌不匹配：锚点永不下发学生")


def _reservation_view(reservation) -> dict:
    return {
        "reservation_id": reservation.reservation_id,
        "session_id": reservation.session_id,
        "stage": reservation.stage,
        "units": reservation.units,
        "state": reservation.state,
        "cost_cny": reservation.cost_cny,
    }


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
