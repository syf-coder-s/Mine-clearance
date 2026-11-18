# 排雷兵项目整合版 v2.0

这是排雷兵多智能体代码审查训练系统的交付包，包含可部署源码、学生网页前端、RAGFlow 接入实现、视觉方案和总体方案文档。

相对 v1.4 的主要变化：新增整套学生网页前端（`frontend/`，登录 / 训练工作台 / 报告 / 历史 / 能力分析 / 系统状态）、前后端同源部署、前端接口文档、部署操作指南，测试从 144 项增加到 163 项。

## 目录

```
排雷兵-项目整合版-v2.0-交付/
├── README-整合说明.md              本文件
├── 交付清单.md                     包内文件清单与校验信息
├── docs/
│   └── 排雷兵-多智能体总方案-v2.0.html   总体方案（v2.0）
├── 配置说明/
│   └── .env.example                配置模板（与源码内 .env.example 相同）
├── 视觉方案/                       前端视觉选型：4 套方向、落地清单、实机截图
└── Mine-clearance-main/            可部署源码
    ├── src/                       Python 编排层（后端）
    ├── tests/                     163 项单元测试
    ├── scripts/                   冒烟与评测脚本
    ├── frontend/                  学生网页（React + Vite）
    ├── frontend-api-doc/          前端接口契约文档与 HTML 版
    ├── docs/                      部署、RAG、上游接口、部署操作指南
    ├── Dockerfile / compose.yaml  Docker 部署
    ├── start.ps1 / stop.ps1       启停脚本
    ├── dev.ps1                    源码直跑后端（调试用）
    ├── README.md                  技术说明
    └── 部署说明.md                 本机部署与验收记录
```

## 本地启动（Docker，推荐）

```powershell
cd Mine-clearance-main
Copy-Item .env.example .env    # 然后按 部署操作指南 填密钥
.\start.ps1
```

启动后访问：

- 学生网页：`http://localhost:8010/`
- API 文档：`http://localhost:8010/docs`
- 健康检查：`http://localhost:8010/v1/health`

停止服务：`.\stop.ps1`（保留证据卷，不要用 `docker compose down -v`）。

第一次部署、填密钥、常见报错，看 `Mine-clearance-main/docs/部署操作指南.md`。

## 前端两种跑法

- 交付/部署：Docker 构建时在容器内 `npm run build`，产物由后端同源托管，页面直接请求 `/v1`，不涉及跨域。
- 本机改界面：`cd frontend` → `npm install` → `npm run dev`（连真实后端 `http://localhost:8010`）；只看看演示数据用 `npm run dev:mock`。

## 验证

- schema：`1.4.0`（数据契约本次未改字段，故不升）
- 完整测试：163 项通过（2026-11-14 复测，Python 3.9）
- 前端：`npm run build` 通过（tsc + vite）
- RAGFlow：`connected=true`
- 已验证 RAG 查询 4 次：主判例库 2 次、缺陷模式库 1 次、正确代码反例库 1 次
- 最终选中参考：主判例 3 条、缺陷模式 1 条、正确反例 1 条
- 错误雷型过滤：5 条
- 去重参考：5 条
- Agent 实际参考字符：4090

## Agent 与 RAG 库绑定

| Agent | 使用的库 | 作用 |
|---|---|---|
| Builder | 主判例库、正确代码反例库 | 生成有代表性的正确基线和题面 |
| Planter | 主判例库、缺陷模式库 | 按雷型埋入单一真实缺陷 |
| Probe | 不直接使用 RAG | 以实际运行结果验证原版通过、埋雷版失败 |
| Adversary | 主判例库、缺陷模式库 | 生成有针对性的对抗追问，不直接泄露答案 |
| Judge | 三个库 | 对照错误模式、正确边界和修复证据，辅助 L0-L4 判级 |
| Reporter | 读取 `rag_usage` | 展示检索、选中、过滤、去重和实际参考字符统计 |

数据集 ID 和详细机制见 `docs/` 下的总体方案 HTML。

## 包内不含什么

为了让压缩包能直接发出，以下内容已剔除（都可在新机器上重新生成，不含任何项目成果）：

| 剔除项 | 原因 / 恢复方式 |
|---|---|
| `frontend/node_modules/` | 依赖缓存，进 `frontend/` 跑 `npm install` 重新装 |
| `frontend/dist/` | 前端构建产物，Docker 构建时自动生成；本机可 `npm run build` |
| `__pycache__/`、`*.pyc` | Python 字节码缓存，运行时自动重建 |
| `.env`（真实配置） | 含 API Key，交付包只放 `.env.example` |
| `.screenshots/.tmp`、`.trae-html-share-packages/` | 临时目录、文档分享用的重复 zip |

## 上传安全

本包不包含真实 `.env`、API Key、模型调用审计、证据快照和临时测试目录。部署前请根据 `.env.example` 在本地创建 `.env`，不要把真实密钥提交到公开仓库。

包内 `.env.example` 保留了三个 RAGFlow 数据集 ID 作为默认值（与 `compose.yaml` 一致），如果对方用的是自己的一套库，记得替换。
