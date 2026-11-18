# 前后端接口契约（给 RAG 同事的清单）

按前端实际调用整理（`src/services/*`），只列关键字段，非完整 schema。

## 错误体（所有接口统一）

- 非 2xx 时后端返回 `{ "error": string, "detail": string }`
- 前端统一收敛成 `{ code: error, message: detail }` 展示

## 接口清单

### GET /v1/health

前端依赖字段（`systemService.getHealth` 适配用）：

- `status`（`ok` 才算 API 服务正常）
- `schema_version`
- `llm_provider` / `mock_llm`（true 时前端标注「Mock 回退」）
- `vendor_isolated`
- `calls_per_session_cap`（预算上限）
- `stage_limits`（`judge_decision` / `judge_escalation` / `report` 三项求和 = 结算预留）
- `cost_known` / `cost_budget_cny`
- `rag`（字符串或 `{ backend }`；stub/contract 时前端标注「本地桩」）
- `upstream`（字符串或 `{ mode, base_url }`；fake 时前端标注「内存实现」）
- `probe` / `sessions`

### POST /v1/sessions（开局）

- 请求体：`{}`（后端使用内置题单；前端只传空对象）
- 响应：
  - `session_id`
  - `unverified_items`
  - `budget`：`{ cap, total, remaining, reserve }`（可选附 `cost_cny`、`offline_calls`）
  - `items[]`：
    - `item_id` / `title` / `code`
    - `rounds_done` / `target_rounds`（target_rounds 可能是 2 或 3，前端不写死）
    - `evidence[]`：`{ evidence_id, excerpt, visible_in_code, line_start?, line_end? }`
      （excerpt 只在 `visible_in_code=true` 时非空；line_start/line_end 为埋雷版代码行号，1-based 闭区间）

### GET /v1/sessions/{id}（进度同步）

- 响应（只回进度，不回题目，前端用开局响应的题目缓存承接）：
  - `settled`
  - `unverified_items`
  - `budget`
  - `items[]`：`{ item_id, rounds_done?, target_rounds?, finished? }`

### POST /v1/sessions/{id}/submit（提交审查意见）

- 请求体（与后端 AnswerIn 一致）：
  - `item_id` / `text` / `cited_evidence_ids` / `proposed_fix`
- 响应：
  - `item_id` / `accepted` / `challenge`
  - `reason`：`ok` | `target_reached` | `budget_guard`
  - `round`（本题已完成或预算不足时后端不带）
  - `rounds_done` / `target_rounds` / `finished`
  - `budget`

### POST /v1/sessions/{id}/settle（结算）

- 响应（一次性返回报告，后端不另存）：
  - `session_id`
  - `verdicts[]`：
    - `item_id` / `label`（`defect_present` | `no_defect`）
    - `level`（原始值如 `L0_false_alarm` ~ `L4_repair`，前端收敛为 L0–L4）
    - `confidence` / `escalated` / `rationale`
    - `citation`：`{ precision, recall, supported[], unsupported[], missing[] }`
    - `references[]`：`{ evidence_id, doc_id, chunk_id, char_start, char_end, quote }`
  - `calls` / `cost_cny` / `markdown`
  - 可选：`latency_ms` / `unverified_items` / `cost_known` / `report_fallback` / `budget` / `stage_calls` / `rag_usage` / `trace`

## 关键约定

- CORS：后端需要允许前端 origin（默认 `http://localhost:5173`、`http://127.0.0.1:5173`，其他 origin 走 `MC_CORS_ORIGINS`）
- 前端不使用 SSE；submit 走普通 JSON
- 前端没有登录 / 鉴权，后端不要要求 token
- 前端不保存 API Key（Key 只在后端 .env）
- 后端没有 `GET /report`、没有 `GET /v1/sessions` 列表：报告与历史由前端本地缓存（localStorage）承接，换浏览器会丢
