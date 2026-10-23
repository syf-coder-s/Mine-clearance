# RAG 接口契约

这份文档是**我们和后端检索服务之间唯一的约定**。`src/mineclearance/rag/client.py` 是它的实现，`tests/test_rag.py` 是它的可执行版本——两边对不上，以测试为准。

先讲清一件事：**RAG 在这套系统里不占在线预算**。检索只在离线准备阶段发生（生成 → 埋雷 → 封印），在线阶段一次检索请求都不发；裁判核验只按 `evidence_id` 取回已封存的片段。所以「RAG 慢」不会拖垮在线体验，「RAG 挂」也不会让整场训练开不了局——客户端会自动降级到本地桩。

## 一、传输约定

| 项 | 约定 |
|---|---|
| 基址 | `RAG_BASE_URL`，为空时**不构造 HTTP 客户端**，直接用本地桩 |
| 认证 | `Authorization: Bearer $RAG_API_KEY`，`RAG_API_KEY` 为空则不带这个头 |
| 编码 | 请求与响应均为 `application/json`，UTF-8，中文不转义 |
| 超时 | `RAG_TIMEOUT_S`，默认 2 秒。检索挂在关键路径上，慢一次就把一场 15 分钟吃掉一块 |
| 重试 | 连接类错误重试 1 次；HTTP 4xx / 5xx **不重试**，直接判后端有问题 |
| 出错 | 任何非 200、返回体缺字段、类型不对，一律包成 `RAGError` 抛给上层 |

后端只要保证 **200 + 下面的 JSON 形状**，其余（切分粒度、检索算法、向量库选型）我们不关心。

## 二、五个端点

### 1. 写入文档

```
POST /v1/index
{"doc_id": "item-1:original", "text": "<原始材料全文>", "language": "python"}
→ {"chunks": 4}
```

`chunks` 是切出来的块数，用于离线阶段核对「这份材料确实被索引进去了」。写入是**幂等覆盖**语义：同一个 `doc_id` 再写一次，旧块必须全部作废。

一个硬约束：`index` 的入参里**没有**「学生作答」这个字段。从类型上就不存在把学生答案写进索引的路径——否则下一场训练的学生能检索到上一场的答案。

### 2. 召回

```
POST /v1/retrieve
{"query": "在有序数组里找最接近目标值的元素 boundary python", "top_k": 10, "doc_id": "item-1:original"}
→ {"items": [ { ...块... } ]}
```

块对象：

```json
{
  "evidence_id": "ev_931f1717f299",
  "doc_id": "item-1:original",
  "chunk_id": "c_3",
  "text": "        if abs(value - target) <= abs(best - target):\n            best = value",
  "char_start": 141,
  "char_end": 208,
  "score": 0.87
}
```

三条要求：

- `doc_id` **可能给也可能不给**。给了就必须只在该文档内召回，不许串到别的题。预取阶段我们一定给——不给的后果是某道题的引用指向了另一道题的代码，这个 bug 出现过一次。
- `char_start` / `char_end` 是**原文中的字符偏移**，且必须满足 `len(text) == char_end - char_start`。我们会校验这一条，对不上就当返回体不合契约。
- `query` 是**原样**的查询串，由 `rag.as_query()` 一次性拼好，不做在线改写、不做多跳。别在后端又加一层查询扩展，两边各扩一次就重复了。

### 3. 按 id 取回证据

```
GET /v1/evidence/{evidence_id}
→ {"evidence_id": "...", "doc_id": "...", "chunk_id": "...",
   "char_start": 141, "char_end": 208, "quote": "<该片段原文>"}
```

这是**封印之后唯一的读路径**。裁判核验引用、结算页回显原文，走的都是它。

### 4. 封印

```
POST /v1/seal
→ {}            # 任何 2xx 均可
```

调用之后，后端**必须**让 `POST /v1/index` 与 `POST /v1/retrieve` 返回错误。我们这一侧已经先拦了一道（`HttpRAG` 内部有 `_sealed` 标记，封印后本地就抛 `IndexSealed`），后端这一道是防「客户端绕开我们直接打后端」。两条都要有，不能只靠客户端。

`seal` 幂等，重复调用不报错。

### 5. 检索摘要（可选）

不给也行。我们打日志时想区分「真的用了后端」和「悄悄降级到桩了」，如果你有健康检查接口，在 `RAG_BASE_URL` 下暴露即可。

## 三、`evidence_id` 怎么来的

由位置决定，不是后端随机生成的：

```python
"ev_" + sha256("%s\x00%d\x00%d" % (doc_id, char_start, char_end))[:12]
```

这么做的理由：同一份材料重跑一次，块的 id 还是同一个。题库缓存命中时我们靠 `_rebind_evidence()` 把旧 id 重新锚到新文档上，id 稳定这条不成立就没法复用。

**后端可以自己生成 id**，但必须满足「同一 `(doc_id, char_start, char_end)` 永远得到同一个 id」，否则引用核验会莫名其妙地失败。

## 四、封印之后的三条规矩

1. 不能重新召回。想「再查一次」的代码在类型层面就写不出来：在线阶段发给裁判和对抗方的是 `SealedView`，它只有 `fetch()`，**没有** `retrieve`。
2. 不能改索引。`index()` 在封印后抛 `IndexSealed`，这是设计违规，不是运行时异常，不该被 `try/except` 吃掉。
3. 学生产出永不入库。见上。

## 五、后端连不上会怎样

`ResilientRAG` 是外壳，第一次任何 `RAGError` 就切到 `LocalStubRAG`，并把此前写过的文档**按原顺序重放进桩**，避免「前半场命中、后半场全空」这种更难看的状态。`summary()` 会给出：

```json
{"backend": "HttpRAG", "degraded": true, "degrade_reason": "连不上检索后端 ...", "sealed": true}
```

现场演示最怕「后端没起」。降级是**默认行为**，不需要开关；要排查「到底连没连上」，看 `summary()["degraded"]` 就行。

## 六、我们这一侧的代理（给前端用）

浏览器**不允许**直连检索后端——那等于把 `RAG_API_KEY` 发到浏览器里。所以 `api/store.py` 做了两层代理，而且两个方向**故意不对称**：

| 端点 | 是否代理 | 为什么 |
|---|---|---|
| `POST /v1/retrieve` | 代理 | 会话内调用时走的是**已封印**的客户端，封印后直接 409，改不了索引 |
| `GET /v1/evidence/{id}` | 代理 | 只读，封印后仍可用，结算复盘要靠它 |
| `POST /v1/index` | **不代理** | 索引只在离线准备阶段由主链写。前端能写就等于能改证据链 |

代理的请求体与响应体：

```
POST /v1/retrieve
{"query": "...", "top_k": 5, "doc_id": "item-1:original", "session_id": "s_xxx"}
→ {"scope": "s_xxx", "sealed": true, "items": [ ...块... ]}

GET /v1/evidence/{id}?session_id=s_xxx
→ {"evidence_id": "...", "doc_id": "...", "chunk_id": "...",
   "char_start": 141, "char_end": 208, "quote": "..."}
```

`session_id` 省略时走「题库作用域」，用于离线建库与调试；带 `session_id` 时走那场会话的客户端，封印后返回 409 `Sealed`。

再看一层：**开局响应里证据片段是空的**。`excerpt` 只在「这段字在埋雷版代码里也看得到」时才回显，否则只给 `evidence_id` 和 `visible_in_code: false`。证据取自原版，回显原文等于把正确答案摆出来——学生能引用编号，但结算之后才看得到原文。这是 `tests/test_api_store.py::LeakTest` 守着的东西，不是 UI 约定。

## 七、对接清单

后端同学要实现的最小集合：

- [ ] `POST /v1/index` 能写入并按 `doc_id` 覆盖
- [ ] `POST /v1/retrieve` 支持 `doc_id` 过滤，返回 `char_start` / `char_end` 与 `text` 严格对齐
- [ ] `GET /v1/evidence/{id}` 返回 `quote`
- [ ] `POST /v1/seal` 之后，前两个端点返回非 2xx
- [ ] 中文能正常返回（不要转成 `\uXXXX` 也问题不大，我们要的是解出来的结果一致）

自测：

```powershell
python -m unittest tests.test_rag -v
python scripts/smoke.py        # 走本地桩，不碰后端
```

真要连后端，把 `RAG_BASE_URL` 填上再跑一次 `smoke.py`；开头那行「检索后端：」会告诉你用的是谁、有没有悄悄降级到本地桩。

## 八、锚点同源与下发隔离

### 1. 锚点：一场训练只有一份判例集合

「锚点」= 一道题在 `seal` 时刻冻结的证据集合（`doc_id` + 该题的 `ev_id` 闭集）。三条规矩：

- **裁判判级与对抗质询吃的是同一份锚点**。裁判升级档读的封存证据（`view.fetch`）与对抗方检索到的判例必须同源——不存在「裁判看 A 套判例、对抗引 B 套证据」的两套口径。
- 对抗方如需在线检索（case 库语义），范围**限定在该题锚点集合内**取 top 块：`doc_id` 过滤之外，后端应再用该题已封印的 `ev_id` 闭集做一道 allowlist。锚点外的证据返回即为越权（见冒烟三断言）。
- 锚点在 `seal` 后不可增删。要加判例 = 重新开局，不能在一场训练中途换判例集合。

### 2. 锚点永不下发给学生

锚点里有 `trigger` / `fix` / `planted` 这类「答案侧」信息，随题下发等于把雷的位置标给学生。隔离落在两层：

- **HTTP 层**：`/context` 的 role 白名单只有 `item_id / language / title / code / rounds_done / target_rounds / evidence` 七类键。`anchor`、`expected_level`、`planted`、`defects` 出现在学生可见 payload 里即为泄露。
- **代码层**：`ItemSpec.expected_level` 与锚点只在编排内部流转（`_target_rounds`、升级提示词），`tests/test_api_store.py::LeakTest` 以键名白名单 + 禁词双断言守着，不是 UI 约定。

### 3. 一场会话的在线口径

在线阶段（学生入场之后）**零检索请求**：

| 阶段 | 在线 LLM 调用 | 检索 |
|---|---|---|
| 对抗质询 | ≤ 9 | 无（只 `fetch` 封存证据） |
| 裁判决策 | 1 | 无（只吃代码抽取的闭表） |
| 裁判升级 | ≤ 1 | 无（只 `fetch` 封存证据） |
| 复盘报告 | 1 | 无（只读 verdicts 表，纯离线拼装） |
| **合计** | **≤ 12** | **0** |

复盘（report）不检索、不出题、不碰索引——它只消费结算表。任何「复盘还要查一次库」的设计都违反这条口径。

### 4. 契约冒烟三断言（后端验收）

对接联调时按这三条验，任何一条不过不算接通：

1. **状态机**：`/stage` 的 `reserve` 请求缺 `stage` 字段 → `409`（不是 200 + 静默补默认值）。
2. **越权检索**：用 A 会话的凭证检索 B 会话/非本题锚点库 → `403`（不是空结果糊弄过去）。
3. **引用越域**：`judgment` 上报的 `evidence_id` 不在该题封印集内 → `422`（不是照单全收再算 precision）。

这三条对应「状态非法 409、越权检索 403、判分引用校验 422」的错误码口径，也是我方 `Judge` 侧 `citation_report()` 之外的第二道防线——本地核验算 precision/recall，后端核验拒收非法引用，两边都得有。
