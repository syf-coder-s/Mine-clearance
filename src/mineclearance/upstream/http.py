"""把同一套裁决语义打给后端。

契约见 docs/upstream-api.md。与 rag/client.py 的区别只有一处，但很重要：
    HttpRAG 外面套了 ResilientRAG，连不上就退本地桩；
    HttpUpstream 不套任何降级——状态与预算的裁决权只有一份，
    本地再算一遍就等于两边同时说了算。
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Dict, List, Mapping, Optional, Sequence

from .base import (
    Anchor,
    AnchorForbidden,
    BudgetExhausted,
    NotConfigured,
    ReferenceOutOfScope,
    Reservation,
    StageConflict,
    StageTicket,
    UpstreamUnavailable,
    summarize,
)

_STATUS_ERRORS = {
    403: AnchorForbidden,
    409: StageConflict,
    422: ReferenceOutOfScope,
    429: BudgetExhausted,
    501: NotConfigured,
}


def error_for_status(status: int, detail: str):
    """状态码 → 本层异常。单拎出来是为了不启服务也能单测这张映射表。"""
    kind = _STATUS_ERRORS.get(status)
    if kind is None:
        return UpstreamUnavailable("裁决后端 %d: %s" % (status, detail))
    return kind("裁决后端 %d: %s" % (status, detail))


class HttpUpstream:
    def __init__(self, base_url: str, api_key: str = "", *, timeout_s: float = 3.0) -> None:
        if not base_url:
            raise NotConfigured("UPSTREAM_BASE_URL 为空，不应构造 HttpUpstream")
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout_s = timeout_s

    # ---- 锚点 ----

    def sync_session(self, session_id: str, items: Sequence[Mapping[str, object]]) -> None:
        """空实现：锚点由后端在 seal 时自己冻结，我们不发第二次。

        保留方法只为让两种实现同签名，调用方不必分支。
        """

    def anchor(self, session_id: str, item_id: str) -> Anchor:
        body = self._request(
            "GET",
            "/v1/anchor/%s?session_id=%s"
            % (urllib.parse.quote(item_id, safe=""), urllib.parse.quote(session_id, safe="")),
            None,
        )
        try:
            return Anchor(
                session_id=session_id,
                item_id=str(body["item_id"]),
                doc_id=str(body["doc_id"]),
                evidence_ids=frozenset(body["evidence_ids"]),
            )
        except (KeyError, TypeError) as exc:
            raise UpstreamUnavailable("锚点返回体不合契约: %s" % exc) from exc

    def verify_reference(self, session_id: str, item_id: str, evidence_ids: Sequence[str]) -> int:
        body = self._request(
            "POST",
            "/v1/anchor/%s/verify" % item_id,
            {"session_id": session_id, "evidence_ids": list(evidence_ids)},
        )
        return int(body.get("checked", len(evidence_ids)))

    # ---- 状态机 ----

    def propose_stage(self, session_id: str, stage: str) -> StageTicket:
        body = self._request("POST", "/v1/stage", {"session_id": session_id, "stage": stage})
        try:
            return StageTicket(
                session_id=session_id,
                stage=str(body["stage"]),
                previous=str(body["previous"]),
                seq=int(body["seq"]),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise UpstreamUnavailable("状态机返回体不合契约: %s" % exc) from exc

    # ---- 两段式预算 ----

    def reserve(self, session_id: str, stage: str, units: int = 1) -> Reservation:
        body = self._request(
            "POST", "/v1/budget/reserve", {"session_id": session_id, "stage": stage, "units": units}
        )
        return _reservation(body)

    def commit(self, reservation_id: str, cost_cny: float = 0.0) -> Reservation:
        body = self._request(
            "POST", "/v1/budget/commit", {"reservation_id": reservation_id, "cost_cny": cost_cny}
        )
        return _reservation(body)

    def void(self, reservation_id: str) -> Reservation:
        body = self._request("POST", "/v1/budget/void", {"reservation_id": reservation_id})
        return _reservation(body)

    # ---- 观测 ----

    def summary(self) -> Dict[str, object]:
        # 不主动打后端：health 是高频端点，不能因为后端慢就把自己的健康检查拖死。
        return summarize("http", base_url=self.base_url, extra={"degraded": False})

    # ---- 传输 ----

    def _request(self, method: str, path: str, payload: Optional[dict]) -> dict:
        data = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = "Bearer " + self.api_key
        request = urllib.request.Request(self.base_url + path, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_s) as response:
                raw = response.read().decode("utf-8")
                return json.loads(raw) if raw.strip() else {}
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:300]
            raise error_for_status(exc.code, detail) from exc
        except (urllib.error.URLError, TimeoutError, ValueError) as exc:
            raise UpstreamUnavailable("连不上裁决后端 %s: %s" % (self.base_url, exc)) from exc


def _reservation(body: Mapping[str, object]) -> Reservation:
    try:
        return Reservation(
            reservation_id=str(body["reservation_id"]),
            session_id=str(body["session_id"]),
            stage=str(body["stage"]),
            units=int(body.get("units", 1)),
            state=str(body.get("state", "reserved")),
            cost_cny=float(body.get("cost_cny", 0.0)),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise UpstreamUnavailable("预算返回体不合契约: %s" % exc) from exc


__all__: List[str] = ["HttpUpstream", "error_for_status"]
