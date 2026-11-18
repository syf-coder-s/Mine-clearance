# 本地部署与 RAGFlow 判例库

本机通过 Docker Compose 运行后端接口，监听 `127.0.0.1:8010`。接口文档：http://localhost:8010/docs；健康检查：http://localhost:8010/v1/health。

当前配置：真实 RAGFlow 检索 + MiMo / DeepSeek 模型。Builder、Adversary 使用 `mimo-v2.6-flash`；Planter、升级 Judge 使用 `deepseek-v4-pro`；决策 Judge、Reporter 使用 `deepseek-flash`。交付包含后端接口与 `frontend/` 学生网页（React + Vite），Docker 镜像已内置前端构建，见下文「前端访问（同源）」。

型号按本次官方 `/models` 返回配置。MiMo 基址 `https://api.xiaomimimo.com/v1`，使用 `api-key` 请求头；DeepSeek 基址 `https://api.deepseek.com`，使用 Bearer。当前请求显式关闭额外 thinking，最多输出4096 Token，单次超时120秒，不自动重试。模型支持不代表本项目评测已证明质量。

## 启停

先启动 Docker Desktop 和本地 RAGFlow，在项目根目录运行：

```powershell
.\start.ps1
```

停止本项目：

```powershell
.\stop.ps1
```

已有 RAGFlow 容器保持独立。本项目的 Compose 名为 `mine-clearance`。本机 Docker Desktop 经 `host.docker.internal` 转发返回 502，因此本项目加入已有 `docker_ragflow` 网络，通过 `http://ragflow-gpu` 直接访问 RAGFlow 容器，不依赖宿主机转发。若重建 RAGFlow 改了网络或服务名，无需改 `compose.yaml`：在 `.env` 里用 `RAGFLOW_DOCKER_NETWORK` 覆盖网络名、用 `RAGFLOW_BASE_URL` 覆盖访问地址即可。

## 配置

密钥仅保存在项目根目录 `.env`，不写入镜像、Git、健康响应或证据快照。不要公开 `.env` 或完整的 `docker compose config` 输出。

| 配置项 | 用途 |
|---|---|
| `RAG_PROVIDER=ragflow` | 启用原生 RAGFlow 适配器 |
| `RAGFLOW_BASE_URL` | 宿主机直接调用时为 `http://localhost`；Compose 内默认 `http://ragflow-gpu`，可在 `.env` 覆盖 |
| `RAGFLOW_API_KEY` | RAGFlow API 密钥，仅服务端使用 |
| `RAGFLOW_DATASET_ID` | 本机“判例与反例”库 `ac92d450cbd711f18b868b1ef2314a80` |
| `RAGFLOW_PATTERN_DATASET_ID` | “缺陷模式”库；检索到的规则摘要给对抗方和升级裁判 |
| `RAGFLOW_NEGATIVE_DATASET_ID` | “干扰项”库；正确代码反例仅给升级裁判，避免与缺陷判例混为一谈 |
| `CASE_TOP_K=3` | 每题最终送入 Agent 的判例条数 |
| `CASE_CANDIDATE_K=10` | RAGFlow 先召回的候选条数，再本地重排 |
| `CASE_MIN_SIMILARITY=0.1` | RAGFlow 最低相似度阈值 |
| `PATTERN_CANDIDATE_K=4` / `PATTERN_MIN_SIMILARITY=0.25` | 缺陷模式库的候选数与最低相似度 |
| `NEGATIVE_CANDIDATE_K=4` / `NEGATIVE_MIN_SIMILARITY=0.25` | 干扰项库的候选数与最低相似度 |
| `RAGFLOW_CACHE_TTL_S=300` | 进程内只读检索缓存有效期（秒）；设为 `0` 关闭，缓存按服务、密钥指纹、规范化查询和知识库隔离；空结果不会缓存 |
| `CASE_SNAPSHOT_DIR` | 容器内为 `/app/data/case_snapshots` |
| `MC_INTERNAL_TOKEN` | 内部接口令牌，使用 `x-internal-token` 请求头 |
| `LLM_PROVIDER=openai_compat` | 当前真实模型，改为 mock 可离线演练 |
| `BUILDER_API_BASE/KEY/MODEL` | 出题方的独立模型路由 |
| `BUILDER_AUTH_HEADER=api-key` | MiMo 认证头 |
| `ADVERSARY_API_BASE/KEY/MODEL` | 对抗方独立模型路由 |
| `ADVERSARY_AUTH_HEADER=api-key` | MiMo 认证头 |
| `LLM_API_BASE/KEY` | DeepSeek 接口与密钥 |
| `DECISION_MODEL / REASONING_MODEL` | 决策、复盘 / 埋雷、升级复核 |
| `MC_PROBE=1` | 受限纯 Python 函数独立行为测试 |

旧的 `RAG_PROVIDER=contract` / `RAG_BASE_URL` 对应 `docs/rag-api.md` 自定义接口，与原生 RAGFlow 不通用。

## 证据与判例的区别

本题原始代码在会话内按结构切分，供核验本题事实。共享判例库只用于审查与判级参考，不上传本题代码、学生答案，也不修改库中文档。

准备阶段按题目主题、缺陷类型和语言检索“判例与反例”主库，先取候选，再在项目本地按显式雷型、关键词和向量相似度重排，最终只保留 `CASE_TOP_K` 条。配置了辅助库时，再分别检索“缺陷模式”和“干扰项”：前者作为审查口径参考提供给对抗方与升级裁判；后者只提供给升级裁判，并显式标为正确代码反例。辅助库召回失败不会阻断主库检索，但不会伪报命中。检索不修改 RAGFlow 原库；每题各类证据均绑定到内部快照，不会出现在学生开局响应。

结算响应新增 `rag_usage`：包含后端连接状态、检索请求数、各库召回/选中统计、去重与过滤统计，以及逐题绑定的主判例/缺陷模式/正确反例数量。复盘 Markdown 也会显示 RAG 使用概览；只展示统计，不下发共享判例正文或内部证据编号。

内部参考进入模型前会压缩为标题、雷型/判级关键词和有限长度摘要，避免把其他题的完整代码塞进提示词。`/v1/health` 的 `rag.retrieval_stats` 会记录各用途库的请求数、召回块数、最终选中数、平均相似度和缓存命中；`empty_results_not_cached` 记录被主动跳过的空结果缓存，避免短暂故障污染后续会话。`rag.case_rerank.mismatch_filtered` 与 `rag.quality_stats.wrong_type_filtered` 记录雷型冲突过滤数，`duplicate_references` / `cross_document_duplicates` 记录按正文 SHA256 去重数，`agent_reference_chars_by_agent` 记录最终实际发送给各 Agent 的参考行字符数。这些统计只用于诊断，不会下发给学生；参考正文不会为统计而复制进统计字段。

封存后，对抗方和升级裁判只读取本场保存的同一组快照，不再在线检索。决策档仍只读闭集抽取表。判例的字符位置指向保存的 chunk 正文，原 dataset/document/chunk ID 与 SHA256 同时保存；该位置不是源 Markdown 文件的偏移。

学生只能引用本题原始代码证据编号；越域引用返回 422。结算前读取证据原文返回 403；结算后可读取本会话代码证据。内部判例不会通过学生证据接口下发。会话内再次检索返回 409。无会话的建库检索和证据读取须携带内部令牌。

## 前端访问（同源）

后端 Docker 镜像在构建阶段用 Node 容器跑 `npm run build` 生成前端，并在 `/` 直接托管 `dist`（SPA 回退）。前端以 `VITE_API_BASE_URL` 空串构建、请求同源 `/v1/*`，不产生跨域，也不依赖 CORS 白名单；部署机器无需预装 Node。访问 http://localhost:8010/ 即为前端页面，`/docs` 仍是 Swagger。

如需在宿主机单独调试前端（热更新），才回到 `frontend/` 用 `npm run dev`（读 `.env`，直连 http://localhost:8010，走 CORS 白名单）。

## 使用接口

在 Swagger 中依次操作：

1. `POST /v1/sessions`，请求体 `{}`，得到 `session_id`、题目和可引用证据编号。
2. `POST /v1/sessions/{session_id}/submit`，提交 `item_id`、`text`、`cited_evidence_ids` 和可选 `proposed_fix`。按响应的 `target_rounds` 完成各题。
3. `POST /v1/sessions/{session_id}/settle`，得到判级、引用核验、复盘和调用分布。

## 存储与边界

证据快照存于 Docker 命名卷 `mine-clearance_evidence`。`docker compose stop` 和普通 `down` 保留该卷；不要用 `down -v`，它会删除快照。会话、题库和预留裁决服务仍在内存中，重启后不能继续原会话，快照不等于会话恢复机制。默认使用单 worker。

`/v1/health` 的 `status=ok` 表示进程可响应；`rag.connected` 是最近一次本进程检索的连接状态，开局前为 false，不是持续探测。判断真实接通应开局成功，并同时看到 `rag.connected=true`、`sealed=true`、`snapshot_saved=true`。Mock 状态会通过 `mock_llm=true` 明示。

真实出题返回 source 和独立 tests，Planter 只能修改 source。PurePythonProbe 要求至少3个 assert；两版代码先通过 AST 限制，再在不带密钥的隔离 Python 子进程中执行同一套测试。原版须通过，埋雷版须出现可确认的测试失败；语法错误、执行初始化失败或超时不当成埋雷成功。当前仅支持受限纯函数小题，不是通用不可信代码沙箱，也不支持任意 API、网络、文件类题目。全部题被剔除时，真实 API 开局返回502。

当前未核实模型单价，`cost_known=false`；`cost_cny=0` 表示未估价，不能当作免费，也不能据此保证0.08元预算。调用次数限制有效，离线出题/埋雷单独计数。Router 在服务端内存记录每次请求的型号、提示词、输出、Token、耗时和错误；含教师答案的审计不会通过学生接口下发。Reporter 失败回退本地模板时，结算响应 `report_fallback=true`。

预留 `/v1/stage`、`/v1/budget/*` 仍为独立内存裁决接口，尚未接入外部权威裁决后端。

## 真实模型与判例消融验收

```powershell
docker compose exec -T api python scripts/evaluate_live.py
```

这是付费真实请求：先生成3题、行为复核并完成会话，再对3个固定标注样本各跑有/无判例的质询和单次升级复核。原始代码证据保持一致；无判例条件只移除内部 `case_evidence_ids`。固定样本中的复核是强制诊断，不等同于正常策略自动触发升级，不计入前一完整会话的12次预算。

每次输出到证据卷 `/app/data/live_evaluation/时间戳/`，包含逐请求明细、固定样本、测试结果、召回文本/分数及CSV对比。目录含教师答案，仅用于内部验收。小样本单次结果不能证明稳定收益；检索成功、提示词读到与效果改善需要分别判断。引用指标只检查编号属于本题，不能代替引用语义核实。

## 检查命令

```powershell
docker compose ps
docker compose logs --tail 50 api
docker run --rm mine-clearance:local python -m unittest discover -s tests -t .
docker run --rm mine-clearance:local python scripts/smoke.py
```

单元测试不需要真实密钥，原生协议测试使用临时 HTTP 服务。冒烟脚本默认是纯离线 Mock 验证，真实 RAGFlow 是否连接应以已部署服务的实际开局和健康响应为准。
