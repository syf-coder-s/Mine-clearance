# 排雷兵 · Mine-clearance

面向「AI 生成代码审查能力训练」的多智能体编排框架。学生是对手，系统负责出雷、陪着辩、最后判级。

本仓库是**编排层**的代码骨架，配套《排雷兵》主方案与《编排实现文档》。当前状态：全链路可离线跑通（Mock 模型 + 本地 RAG 桩）；真实模型与真实 RAG 服务通过配置接入，调用方代码不改。

## 为什么是这个形状

一句话：一条主链加一个环，不做运行时拓扑搜索。

离线建设（生成、埋雷、封印证据）不占在线预算；在线只跑「学生审 → 对抗 2 至 3 轮」的环，三段之后一次结算。所有速度优化都在调用位置上（题库缓存、逐项流式、深度 1 预取、按难度伸缩轮次），一个都不在模型层。

## 四个角色

| 角色 | 在哪 | 每次会话的模型调用 |
|---|---|---|
| 生成 builder | 离线 | 0（不计入当次训练） |
| 埋雷 planter | 离线 | 0，且必须过「原版通过、埋雷版失败」复核 |
| 对抗 adversary | 在线 | 每段每轮 1 次，三段合计 6 至 9 |
| 裁判 judge | 在线结算 | 决策层 1 次，升级余量 0 至 1 次 |
| 过程报告 report | 在线结算 | 1 次 |

上界 12，与申报表的硬上限一致；预算守卫在 `budget.py` 里强制执行（放在包根，因为 llm 与 agents 两层都要查额度），不是靠自觉。

## 目录

```
src/mineclearance/
  config.py              环境变量与默认值，一个冻结的 Settings
  schemas.py             冻结的数据契约（证据、雷、作答、判级、报告）
  budget.py              调用额度守卫，超了抛异常
  llm/                   模型抽象：Protocol、Mock、双档路由
  rag/                   RAG 客户端（HTTP）与本地桩，含封印规则
  agents/                离线（生成 + 埋雷）与在线（对抗 + 裁判 + 报告）
  orchestration/         题库缓存与主链
  api/                   Web 层：store.py 是会话状态机（纯标准库），main.py 是 FastAPI 薄壳
tests/                   stdlib unittest，不依赖第三方包
scripts/smoke.py         打印一次完整会话的调用轨迹
docs/rag-api.md          后端检索服务的接口契约
```

## 快速开始

核心链路只依赖标准库，装不装依赖都能跑。

```powershell
python scripts/smoke.py
python -m unittest discover -s tests -t . -v
```

跑 Web 接口需要额外依赖：

```powershell
pip install -r requirements.txt
uvicorn mineclearance.api.main:app --reload
```

## 接入真实模型

只改 `.env`，不改代码：

```ini
LLM_PROVIDER=openai_compat
LLM_API_BASE=https://api.example.com/v1
LLM_API_KEY=sk-xxx
DECISION_MODEL=<小模型>
REASONING_MODEL=<推理档模型>

# 对抗方单独一家。留空则复用推理档，会话照常跑，
# 但 /v1/health 的 vendor_isolated 会是 false——复核等于自己查自己。
ADVERSARY_API_BASE=
ADVERSARY_API_KEY=
ADVERSARY_MODEL=
```

`llm/router.py` 负责按档位分发。决策层只吃抽取出来的结构化表，不吃学生的原始文本；这是精度设计，不是省钱设计。

**对抗方与裁判不得同源**：升级裁判复核的正是对抗方参与过的对话，同一个模型既当质询者又当复核者，这次复核等于自己查自己。所以对抗是独立一档（`STAGE_TIER["adversary"]`），配第二家厂商时才算真正隔离；只配一家也能跑，但 `/v1/health` 会如实写 `vendor_isolated: false`——降级可以，假装做到了不行。

## 接入 RAG

`RAG_BASE_URL` 留空时自动落到本地桩 `StubRAG`，用于开发和测试。填写后走 HTTP，契约见 `docs/rag-api.md`。

三个接入点里只有裁判核验在关键路径上，且只按 `evidence_id` 取回，不发起新检索。索引一旦 `seal()`，再写就抛 `IndexSealed`，这条规则写死在代码里。

## Web 接口

`api/store.py` 是会话状态机，只依赖标准库，**不装 fastapi 也能测**（`tests/test_api_store.py` 直接驱动它）。`api/main.py` 只做 JSON 与调用之间的翻译，里面没有判级、没有预算计算。

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/v1/health` | 版本、模型档位、预算上限、探针类型、检索后端是否降级 |
| POST | `/v1/sessions` | 开局，返回三道题（只有埋雷版代码） |
| GET | `/v1/sessions/{id}` | 读进度，不花钱 |
| POST | `/v1/sessions/{id}/submit` | 提交一轮作答；带 `Accept: text/event-stream` 则走 SSE 流式 |
| POST | `/v1/sessions/{id}/settle` | 结算，产出判级、引用原文与复盘 |
| POST | `/v1/retrieve` | 预留的检索代理（读方向） |
| GET | `/v1/evidence/{id}` | 按证据编号取回片段 |
| POST | `/v1/stage` | 预留的裁决接口：提议下一步，非法转移回 409 |
| POST | `/v1/budget/reserve` `/commit` `/void` | 预留的两段式预算 |
| GET | `/v1/anchor/{item_id}` | 锚点，仅内部令牌可读（默认 403） |
| POST | `/v1/anchor/{item_id}/verify` | 引用越域回 422 |

后四个是给后端对接用的预留接口，默认走内存实现 `FakeUpstream`，契约见 `docs/upstream-api.md`。主链尚未调用它们——先把口径对齐，再接进 `Session.submit` / `settle`。

这一层只守三件事：发给学生的包是**白名单字段**（没有原版、没有 diff、没有 rubric）、证据原文在结算前**一个字都不回显**、会话**单向**（结算后 submit 一律 409）。领域错误带状态码（404 / 409 / 422 / 502），壳里不出现 500 兜底。

## 文档

- `docs/rag-api.md` —— 后端检索服务要实现什么、`evidence_id` 怎么生成、封印之后哪些调用必须被拒
- `docs/upstream-api.md` —— 裁决层：状态机、两段式预算、锚点，以及 409 / 403 / 422 的判定口径


## 未做的事

- 不做运行时建图与去中心化路由（GoA、GraphPlanner、AgentNet）
- 不做 KV 级通信（模型是闭源 API，拿不到 KV）
- 不做在线查询改写与多跳检索（会把 12 次预算吃掉三次）
- 不做投机预跑（命中率约 55%，一半算力白烧）

## 许可

代码 MIT；题库、rubric 细则与评测数据不在本仓库。
