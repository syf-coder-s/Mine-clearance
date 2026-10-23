# 裁决层接口（预留）

这份文档是**我们和后端之间关于「谁能决定什么」的约定**。实现：`src/mineclearance/upstream/`，可执行版本：`tests/test_upstream.py`。

先说清楚这一层存在的理由：主链里有三件事不许由 agent 自己说了算——**下一步能不能走**、**这次调用还给不给批**、**这道题冻结了哪些证据**。agent 只能提议，裁决权在后端。`upstream/` 就是那个裁决方的接口。

两种实现，切换只看一个环境变量：

| `UPSTREAM_BASE_URL` | 实现 | 用途 |
|---|---|---|
| 空 | `FakeUpstream`（内存） | 默认。没接后端也能把七个端点跑通、能写单测 |
| 有值 | `HttpUpstream` | 打到后端，HTTP 状态码原样映射成本层异常 |

**这一层刻意不降级。** 检索挂了可以退到本地桩，因为少一点证据还能继续判；状态机或预算挂了再退到本地实现，等于一边问后端一边自己说了算——那不是降级，是假装。所以 `HttpUpstream` 出错就抛，由壳层翻成 502。

## 一、错误码口径

| 场景 | 状态码 | 异常类 |
|---|---|---|
| 状态非法（缺 `stage`、未登记阶段、结算后还想对抗） | `409` | `StageConflict` |
| 额度不足（阶段上限或会话总额度） | `409` | `BudgetExhausted` |
| 越权取锚点（拿 A 会话凭证读 B 会话的题） | `403` | `AnchorForbidden` |
| 引用越域（`evidence_id` 不在该题封印集内） | `422` | `ReferenceOutOfScope` |
| 后端连不上 / 返回体不合契约 | `502` | `UpstreamUnavailable` |
| 未配置就调用 | `501` | `NotConfigured` |

`409` 一律不用 `422` 顶替：`422` 是「参数格式不对」，`409` 是「格式没错，但现在不能这么做」，前端的处理不一样。

## 二、状态机

状态名与预算阶段同名，一次提议既决定流程走向，也决定从哪个额度池里扣：

```
open ──▶ adversary ──▶ judge_decision ──▶ judge_escalation ──▶ report
            │  ▲              │                  │
            └──┘              └──────────────────┴──▶ report
```

| 当前 | 允许的下一步 |
|---|---|
| `open` | `adversary` |
| `adversary` | `adversary`（自循环，每题至多 3 轮）、`judge_decision` |
| `judge_decision` | `judge_escalation`、`report` |
| `judge_escalation` | `report` |
| `report` | 无（终态） |

```
POST /v1/stage
{"session_id": "s_xxx", "stage": "adversary"}
→ {"session_id": "s_xxx", "stage": "adversary", "previous": "open", "seq": 1}
```

缺 `stage` 必须回 `409`，**不是** `200 + 静默补默认值`。

## 三、两段式预算

先占后花。`reserved` 期间额度已被占住但未记账，`commit` 之后才算花掉，`void` 把占住的额度还回去。这样并发的两条支路不会同时看到「还剩 1 次」然后都花掉。

```
POST /v1/budget/reserve   {"session_id": "s_xxx", "stage": "adversary", "units": 1}
→ {"reservation_id": "rsv_0001", "session_id": "s_xxx", "stage": "adversary",
   "units": 1, "state": "reserved", "cost_cny": 0.0}

POST /v1/budget/commit    {"reservation_id": "rsv_0001", "cost_cny": 0.0012}
→ {..., "state": "committed", "cost_cny": 0.0012}

POST /v1/budget/void      {"reservation_id": "rsv_0001"}
→ {..., "state": "voided"}
```

额度不放大：阶段上限 `adversary 9 / judge_decision 1 / judge_escalation 1 / report 1`，会话总额 `12`。这三个数字只在 `budget.py` 与 `config.py` 各出现一次。

## 四、锚点

「锚点」= 一道题在 `seal` 时刻冻结的证据集合（`doc_id` + 该题的 `ev_id` 闭集）。

- **同源**：裁判升级档读的证据与对抗方引的判例是同一份锚点，不存在两套口径。
- **不可增删**：`seal` 之后想换判例集合 = 重新开局，中途改一律 `409`。
- **永不下发学生**：锚点里有 `trigger` / `fix` 这类答案侧信息。`/v1/anchor/*` 只对带 `X-Internal-Token` 的调用方开放，令牌留空（默认）时一律 `403`。

```
GET  /v1/anchor/{item_id}?session_id=s_xxx
→ {"session_id": "s_xxx", "item_id": "item-1", "doc_id": "doc_item-1",
   "evidence_ids": ["ev_a", "ev_b"], "count": 2}

POST /v1/anchor/{item_id}/verify
{"session_id": "s_xxx", "evidence_ids": ["ev_a", "ev_c"]}
→ 422 ReferenceOutOfScope（ev_c 不在这道题的封印集里）
→ {"ok": true, "item_id": "item-1", "checked": 2}（全部在集内时）
```

`HttpUpstream.sync_session` 是空实现：HTTP 模式下锚点由后端在 `seal` 时自己冻结，我们不登记第二次。

## 五、怎么接到主链上（现在还没接）

端点已经挂好，但主链**还没有调用**它们——这是刻意的，先让接口和后端对齐，再把调用点插进去。总共两个位置：

1. `orchestration/pipeline.py::Session.submit` 的 `adversary.challenge(...)` 之前：

   ```python
   ticket = self.upstream.propose_stage(handle.session_id, "adversary")
   reservation = self.upstream.reserve(handle.session_id, "adversary")
   try:
       challenge = self.adversary.challenge(...)
   except Exception:
       self.upstream.void(reservation.reservation_id)
       raise
   self.upstream.commit(reservation.reservation_id, cost_cny=...)
   ```

2. `Session.settle` 里判级之前提议 `judge_decision`，升级前提议 `judge_escalation`，复盘前提议 `report`。

接的时候注意：本地 `CallBudget` 不要删。它管的是「这一进程里到底发了几次模型调用」，后端管的是「额度批没批」。两边都要有——本地是防手滑，后端是防绕过。

## 六、验收三断言

联调时按这三条验，任何一条不过不算接通：

1. 缺 `stage` 的 `/v1/stage` → `409`（不是 200 + 默认值）。
2. 用 A 会话凭证读 B 会话的锚点 → `403`（不是空结果糊弄）。
3. 上报的 `evidence_id` 不在该题封印集内 → `422`（不是照单全收再算 precision）。

自测（不碰后端）：

```powershell
python -m unittest tests.test_upstream -v
```
