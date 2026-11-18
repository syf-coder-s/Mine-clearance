# 代码审查对抗训练 · 前端

## 1. 项目简介

- 技术栈：React 19 + TypeScript + Vite 8 + React Router 7
- 职责：训练配置 → 代码审查对抗 → 结算报告 → 本地历史
- 两种数据模式：
  - `live`：请求真实后端（默认，推荐交付方式）
  - `mock`：内置演示数据（`npm run dev:mock`）

## 2. 运行要求

- Node `^20.19.0` 或 `>=22.12.0`（Vite 8 要求）+ npm —— 源码运行需要
- 或 Python 3.9+（仅标准库）—— 只跑预构建 dist 时（见方式 B）

## 3. 后端前置条件

- 后端已在 `http://localhost:8010` 启动
- 后端 `.env` 已补真实 API Key（Key 只放在后端，前端不配置）
- `GET /v1/health` 返回 `status=ok`
- 真实模式应看到 `mock_llm=false`、rag 已接真实库（系统状态页不再显示「Mock 回退 / 本地桩」）

## 4. 运行方式

### 方式 A：源码运行（有 Node 的同事）

```bash
# 在 frontend 目录，不要把 node_modules 拷来拷去
npm ci
# 确认 .env（参考 .env.example）：
#   VITE_DATA_MODE=live
#   VITE_API_BASE_URL=http://localhost:8010
npm run dev
# 打开 http://localhost:5173
```

### 方式 B：预构建 dist + serve.py（只有 Python 的同事）

```bash
# 1) 在开发机（有 Node）上执行：
npm run build
# 2) 把 dist/ 和 serve.py 一起拷到目标机器
# 3) 在目标机器上：
python serve.py --port 5173
# 打开 http://127.0.0.1:5173
```

注意：dist 里的 `VITE_*` 是构建时写死的，改 .env 后必须重新 `npm run build`。

### 方式 C：后端同源托管（可选）

- 把 `dist/` 交给后端用 FastAPI `StaticFiles` 挂到 8010
- 前端构建时 `VITE_API_BASE_URL` 留空并重新 build（空串 = 同源请求）
- 这样没有 CORS 问题

## 5. 环境变量

| 变量 | 值 | 说明 |
|---|---|---|
| `VITE_DATA_MODE` | `live` / `mock` | `live` 请求真实后端；`mock` 使用内置数据。只有显式 `mock` 才是演示模式，未配置/空串/拼错一律按 `live` |
| `VITE_API_BASE_URL` | `http://localhost:8010` 或空 | 后端地址；空表示同源请求 |

`npm run dev` 读 `.env`；`npm run dev:mock` 读 `.env.mock`。

## 6. CORS 与端口

- 后端默认允许 `http://localhost:5173` 和 `http://127.0.0.1:5173`
- 如果前端用 4173 / 8080 / 局域网 IP / 域名，必须让后端设置 `MC_CORS_ORIGINS` 加上对应 origin
- 如果前后端不在同一台机器：后端 compose 目前绑定 `127.0.0.1:8010`，需要改成 `0.0.0.0` 并放行防火墙

## 7. 真机验证步骤

1. 打开首页，顶栏显示「已连接」而不是「演示模式」
2. 打开系统状态页，显示「真实后端」，服务状态符合实际
3. 新建训练 → 能拿到题 → 提交一轮 → 结算 → 报告 → 历史
4. 浏览器 Console 无 CORS / 网络错误

## 8. 已知限制（务必了解）

- 训练会话保存在后端内存，后端重启后旧会话不可恢复
- 报告只在结算时缓存在当前浏览器，换浏览器 / 清缓存后无法找回
- 历史列表由本机浏览器维护，后端没有 `GET /v1/sessions` 列表接口
- 后端没有 `GET /report` 接口
- 不要清空浏览器 localStorage
- 真实 API Key 只在后端 `.env`，前端永远不配置 Key

## 9. 常见问题

- 顶栏显示「演示模式」：`.env` 或构建时的 `VITE_DATA_MODE` 还是 mock
- 顶栏「后端不可达」：8010 没起 / 地址不对 / CORS 被拒
- 报告 404：当前浏览器没有该会话的结算缓存（换浏览器或清过缓存）
- 页面刷新 404：静态服务器没做 SPA fallback，用 `serve.py`（它已内置）
