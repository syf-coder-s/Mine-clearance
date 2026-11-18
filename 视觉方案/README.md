# 排雷兵 · 整体视觉方案（4 选 1）

> **2026-11-12 已落地**：最终采用「浅色科技版 · 冷白 + 电蓝」，代码已改完（`Mine-clearance-main/frontend`），
> `npm run dev:mock` 即可看到。实施清单见文末「已落地：改了哪些文件」。配套实机截图：`shots/ui_*.png`。

预览文件：`visual/` 下的静态 HTML 与效果图，都是**同一套页面结构**换皮，字号与信息层级完全一致，所以选定哪一套都能整套落地，不会只美一页。

- `overview.html` / `shots/overview.png`：四套方向对照总览
- `preview.html?t=a|b|c|d` / `shots/a.png`…`d.png`：1440×900 工作台完整效果
- `fonts/`：已下载好的免费字体子集（可直接进仓库）
- 效果图里的中文是 Noto Sans SC / Noto Serif SC（本机已装），英文数字用 Inter / JetBrains Mono / IBM Plex

---

## 一句话选型

| | 方向 | 气质 | 最适合 | 改动量 |
|---|---|---|---|---|
| **A** | 深空指挥舱 | 暗色 · 安全运营中心 | 代码审查页、系统状态、演示大屏 | 中（需处理暗色下所有状态色） |
| **B** | 暖白判例簿 | 浅色 · 判例文书感 | 报告页、能力分析、对外汇报 | 中（新增衬线标题族） |
| **C** | 石墨琥珀 | 工程仪表盘 · 警戒语义 | 训练主流程、雷型统计 | 中（侧栏转深色） |
| **D** | 原风格精修 | 现有蓝白企业风的精修版 | 想先上线、再局部升级 | 低（只动令牌） |

**推荐组合**：主界面用 **C 石墨琥珀** 或 **D 原风格精修**，报告页单独用 **B 暖白判例簿**（报告要打印/外发，纸感更合适）。A 适合当"大屏/演示模式"的独立主题，不适合作为唯一主题——暗色下 L0–L4 判级、雷型这些语义色要全部重调一轮。

---

## 四套设计令牌（可直接替换 `src/styles/tokens.css`）

### A 深空指挥舱
```css
--bg:#0A101C; --bg-card:#0F1826; --bg-elevated:#131E2E;
--border:rgba(148,178,214,.13); --border-strong:rgba(148,178,214,.22);
--text-main:#E6EEF9; --text-secondary:#93A7C2; --text-tertiary:#657891;
--primary:#5B93FF; --primary-hover:#7AA8FF; --primary-soft:rgba(91,147,255,.14);
--success:#42D39B; --warning:#EDB44F; --danger:#F57D74;
--radius-card:14px; --radius-control:9px;
--font-sans:'Inter','Noto Sans SC',sans-serif;
--font-mono:'JetBrains Mono',Consolas,monospace;
```
要点：卡片靠 1px 半透明亮边 + 极轻内阴影分层，不用大投影；主区顶部一层 8% 主色径向光晕；侧栏比卡片再深一档（`#0C1421`）。

### B 暖白判例簿
```css
--bg:#FAF9F5; --bg-card:#FFFFFF; --border:#E6E1D6;
--text-main:#191C22; --text-secondary:#6B6F77; --text-tertiary:#9A9C9F;
--primary:#4338CA; --primary-soft:#EEEDFB;
--success:#2E7D5B; --warning:#A9762E; --danger:#AF4A40;
--radius-card:16px; --radius-control:10px;
--font-display:'Noto Serif SC','Songti SC',serif;
```
要点：只给 h1/h2 用衬线，正文仍是 Inter，避免整页变"论文"；卡片几乎无阴影，靠 1px 暖灰边分层；表头底色 `#F5F3EC`。

### C 石墨琥珀
```css
--bg:#F3F3F0; --bg-card:#FFFFFF; --border:#DBDBD3;
--text-main:#14161A; --text-secondary:#66696E;
--primary:#C2740B; --primary-hover:#A96307; --primary-soft:#FBEFDD;
--success:#3B7A4E; --warning:#A87417; --danger:#AB3A30;
--radius-card:8px; --radius-control:5px;
--font-sans:'IBM Plex Sans','Noto Sans SC',sans-serif;
--sidebar-bg:#191B1E; --sidebar-active:rgba(240,162,60,.16);
```
要点：侧栏深石墨 + 琥珀选中态，琥珀本身承担"警戒/雷"的语义；表头与分组标签用 10.5px + 0.09em 字距的大写小标；数字全部等宽。

### D 原风格精修（低风险）
```css
--bg:#F4F6FA; --bg-card:#FFFFFF; --border:#E3E8F0;
--text-main:#141B2B; --text-secondary:#5C6B84; --text-tertiary:#8D9AB0;
--primary:#2C5BE0; --primary-soft:#EEF3FE;
--radius-card:14px; --radius-control:9px;
--shadow-card:0 1px 2px rgba(20,29,48,.04), 0 10px 26px -18px rgba(20,29,48,.28);
```
相对现状只改 7 处：① 圆角 12→14；② 阴影改成"大范围低透明"；③ 主色 2563EB→2C5BE0（更沉）；④ 正文 14→13.5、行高 1.6→1.55；⑤ 页面标题 20→21 + 字距 -0.01em；⑥ 表头/标签统一 11px 灰；⑦ 侧栏图标由字符 `▦＋☰◔◉` 换成线性图标。

---

## 字体（全部 OFL，可商用）

| 用途 | 字体 | 来源 |
|---|---|---|
| 英文/数字 | Inter | https://rsms.me/inter/ |
| 中文正文 | Noto Sans SC | https://fonts.google.com/noto/specimen/Noto+Sans+SC |
| 中文标题（仅 B） | Noto Serif SC | https://fonts.google.com/noto/specimen/Noto+Serif+SC |
| 代码/ID/数字 | JetBrains Mono | https://www.jetbrains.com/lp/mono/ |
| 工程感西文（仅 C） | IBM Plex Sans | https://github.com/IBM/plex |

`fonts/` 里已放好 woff2 子集（Inter 变量、JetBrains Mono 400/600、IBM Plex Sans 400/600），直接复制进 `src/assets/fonts` 用 `@font-face` 引入即可，不依赖外网 CDN。

## 图标

现在侧栏用的是字符图标（`▦ ＋ ☰ ◔ ◉`），字号一变就错位，是"看起来没做设计"的主要原因。建议换线性图标库：

- **Lucide**（推荐，1300+ 图标，1.75px 线宽，与四套都搭）：https://lucide.dev
- **Phosphor**（更圆润，风格化更强）：https://phosphoricons.com
- 映射：工作台 `layout-grid`、开始训练 `circle-plus`、训练历史 `list`／`history`、能力分析 `chart-line`／`target`、系统状态 `activity`、盾牌 Logo 保持现有自绘 SVG。

---

## 落地清单（按文件）

1. `src/styles/tokens.css` — 整体替换为选定方向的令牌（约 60 行）
2. `src/index.css` — 卡片/按钮/表格/徽标微调：圆角、阴影、表头、hover
3. `src/components/common/Sidebar.tsx` — 字符图标换 SVG 组件（新增 `components/icons.tsx`，约 8 个）
4. `src/components/common/AppLogo.tsx` — 选中态色改 `currentColor`，暗色主题下自适应
5. `src/pages/DashboardPage.tsx` — 欢迎区加 eyebrow 小标 + 主次双按钮；概览卡加迷你趋势条
6. 全局加 `@font-face` + `font-display:swap`，`index.html` 不需要外链

预计 0.5–1 天可全部落完；A/C 因为要重调状态色与代码高亮，多半天。

---

## 材质（可与上面任一配色方向组合）

预览：`materials.html` / `shots/materials.png`。六种「表面质感」，都只用 CSS / 内联 SVG，没有图片资源、不增加请求。

| | 材质 | 观感 | 最搭 | 代价 |
|---|---|---|---|---|
| M1 | 哑光纸 | 米白、无光、极轻颗粒 | B 判例簿 | 低 |
| M2 | 磨砂玻璃 | 半透明、背景透色、内高光 | A 演示大屏 | 中（blur 掉帧） |
| M3 | 暗夜细砂 | 深底 + 颗粒 + 微光 | A 深空舱 | 低 |
| M4 | 拉丝钢 · 硬边 | 小圆角、金属描边、硬阴影 | C 仪表盘 | 低 |
| M5 | 蓝图网格 | 深蓝底 + 24px 网格 + 等宽字 | C / 技术风 | 低 |
| M6 | 柔光拟物 | 同色凹凸、双阴影、无描边 | D 精修版 | 低（仅浅色） |

实现要点（这几条不注意就会"脏"）：

```css
/* 颗粒：叠在卡片上、不要叠在文字上 */
.card::before{
  content:''; position:absolute; inset:0; pointer-events:none; border-radius:inherit;
  background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='140' height='140'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='.9' numOctaves='3' stitchTiles='stitch'/%3E%3CfeColorMatrix type='saturate' values='0'/%3E%3C/filter%3E%3Crect width='140' height='140' filter='url(%23n)'/%3E%3C/svg%3E");
  opacity:.06; mix-blend-mode:multiply;   /* 深色底改 overlay */
}
/* 玻璃：背后必须有颜色，否则看不出来；-webkit- 前缀给 Safari */
.topbar{ background:rgba(255,255,255,.55); backdrop-filter:blur(16px) saturate(140%);
         border-bottom:1px solid rgba(255,255,255,.7); }
/* 网格：线要淡（alpha ≤ .10），且只在背景层 */
.page-wrap{ background-image:
  linear-gradient(rgba(120,200,255,.10) 1px,transparent 1px),
  linear-gradient(90deg,rgba(120,200,255,.10) 1px,transparent 1px);
  background-size:24px 24px; }
/* 拟物：浅色左上、深色右下，卡片与底色同色，不要描边 */
.card{ background:#E9ECF2; border:0;
       box-shadow:8px 8px 20px rgba(163,174,192,.75), -8px -8px 20px rgba(255,255,255,.95); }
```

搭配建议（三个现成组合）：

1. **B + M1 哑光纸**：报告页、可打印，最稳的一套"文书感"。
2. **C + M4 拉丝钢**：主界面，硬边 + 小圆角，像设备操作台。
3. **A + M3 暗夜细砂**：演示 / 大屏模式，颗粒让深色不"塑料"。

避坑：`backdrop-filter` 只用在顶栏、侧栏、弹窗这类少量元素上，表格行里用会明显掉帧；M6 拟物在深色主题下不成立，别硬套。

---

## 演示版（推荐）：深空调度台

效果图：`shots/demo.png`（1920×1080，16:9，投影/录屏原生尺寸），源码 `demo.html`。

对标之后发现，同类产品真正拉开差距的不是配色，而是**"把过程演出来"**：

- 安全平台（Snyk 新版 UI、CrowdStrike 一类）默认深色，因为演示场景多在会议室/大屏，浅色一片白会发灰；强调色只留一个高饱和色，其余全部压低。
- 安全训练平台（HTB / TryHackMe）持续在做的其实是"进度感"：等级、倒计时、连续命中，一眼知道自己在哪。
- AI Agent 类产品现在的主流不是聊天框，而是**流水线 + 状态 + 可追责**：谁跑的、跑到哪、耗时多少、产出什么（[Agent Management Interface Patterns](https://www.lukew.com/ff/2106/agent-management-interface-patterns)）。
- 真正显"设计感"的是**信息编排**：一个大焦点 + 密集但不乱的数据层 + 一条能讲故事的路径，而不是加渐变和玻璃。

所以演示版没有沿用 A 的蓝色，而是把**琥珀色当唯一强调色**（自带"警戒/排雷"语义，且没有同类产品在用它），页面按"一眼看懂发生了什么"重排成四块：

1. **判级焦点（左上）**：104px 的 `L2` + 横向 L0–L4 轨道，投影上 3 米外也读得清。
2. **缺口清单（右上）**：直接写"升到 L3 还缺什么"——2 项已达成、2 项未达成。这比任何图表都更能说明产品价值。
3. **埋雷点 + 参考修复（左下）**：代码 14px（演示可读），缺陷行红色高亮，下面紧跟参考修复的红绿对照，一句"仅作对照 · 不计入你的答案"守住公平性。
4. **智能体流水线（右侧）**：6 个 Agent 的名字没改成花名，而是用 `BASELINE / INJECT / VERIFY / CHALLENGE / GRADE / REPORT` 的小字角色词，加耗时、加运行态的进度条；底部一行"7/12 调用、平均 2.4s"。

**动效只做 3 处**（演示时讲得清，也不掉帧）：
- 判级数字 0→L2 的 0.6s 过渡 + 一次琥珀光晕呼吸；
- 当前 Agent 的进度条匀速推进、状态点在闪；
- 参考修复的红色删除行 → 绿色新增行依次展开。

**为什么它比 A/B/C/D 更适合演示**：A 只是"深色的后台"，这套是"有主角的大屏"——观众视线有落点（L2）、有悬念（还差 1 条证据）、有过程（6 个 Agent 在跑）。上线时它可以做成 `/demo` 独立路由或"演示模式"开关，不影响日常训练页的可读性。

成本：静态样式 + 一条假数据 flow 约 1 天；如果要让流水线真跑起来（SSE 推进状态），再加 1 天。

### 浅色版「象牙调度台」（当前推荐）

效果图 `shots/demo-light.png`，源码 `demo-light.html`。结构和深色版完全一致，只换表面：

```css
--bg:#EFEAE0;        /* 米白纸，不用纯白，投影不刺眼 */
--panel:#FFFFFF;     /* 卡片才是白 */
--line:#E3DCCB;
--ink:#17191E; --ink2:#5E626B; --ink3:#8B8F97;
--amber:#C2410C;     /* 朱砂，替代琥珀：浅底上更沉、更"排雷" */
--teal:#1F7A5C; --red:#BE4034;
```

浅色最容易做平，所以加了四个"撑住设计感"的处理：

1. **底色不用纯白**，用 `#EFEAE0` 米白 + 48px 极淡网格，卡片才是 `#FFF`，层级立刻出来；顶部一条 3px 朱砂线做签名。
2. **大数字用衬线**（Noto Serif SC）：`L2` 是整页唯一的大字号，衬线让它像判决书上的等级，而不是仪表盘读数；正文仍是 Inter，不会整体变"论文体"。
3. **右侧"升到 L3 还缺什么"做成米黄内嵌面板**，不是又一堆白卡片——页面因此有"主区 / 副区"两种表面。
4. **代码区单独一块米白面板**，14px 等宽，缺陷行浅朱砂底 + 左侧 2px 红杆；参考修复紧跟其下，红绿对照。

深色版留作 `/demo` 的大屏模式（会议室投影更抓眼），浅色版当默认演示与日常界面都行。

### 浅色科技版「冷白调度台」（要"一点科技感"时用这个）

效果图 `shots/demo-tech.png`，源码 `demo-tech.html`。思路是**结构不动，只在表面加 5 个很克制的科技信号**，其余全部保持极简：

1. **底色转冷**：`#F4F6FA` 冷白 + 28px **点阵**（不是线网格，点阵更轻）。
2. **强调色只留一个电蓝** `#3157DD`，成功率改用青绿 `#0E9488`；不做第二强调色。
3. **微标全部等宽字体**：`JUDGE · 判级`、`BASELINE / INJECT / VERIFY` 这类小字改成 JetBrains Mono 大写 + 0.16em 字距——这是最省力的"技术感"来源。
4. **四角刻线**：判级卡四角各 12px 的细蓝 L 形，透明度 42%，只在主卡上出现一次。
5. **代码面板做窗口化**：左上三个 7px 圆点（红黄绿降饱和）+ 极浅冷灰底 `#F7F9FD`，像一块 IDE 面板而不是普通卡片。

刻意没做的（这是"不要太浓"的关键）：不用深色块、不用发光文字、不用玻璃拟态、不铺大面积渐变、圆角保持 14px 不变。

想微调就动这三处：点阵密度（28px → 40px 更淡）、四角刻线（删掉即回到纯极简）、强调色（`#4B6BD6` 更含蓄 / `#2563EB` 更常规）。

---

## 下一步

告诉我选 **A / B / C / D**（或"A 的配色 + D 的布局"这类混搭），我直接改代码出可运行版本，并把改动控制在上面清单范围内。

材质单独选也行，格式：`方向 + 材质`，例如 `C + M4`、`B + M1`、`A + M3`。要的话我可以先出一整套组合的 1440 全页效果再动手。

---

## 已落地：改了哪些文件

### 设计系统
| 文件 | 作用 |
|---|---|
| `src/styles/tokens.css` | 全量替换为冷白 + 电蓝令牌（底色、线、语义色、代码色、圆角、阴影、字体栈） |
| `src/styles/fonts.css` | 新增：自托管 Inter（变量）与 JetBrains Mono 400/600，`font-display: swap` |
| `public/fonts/*.woff2` | 字体文件（Inter 47KB、JBMono 21KB×2），不依赖外网 CDN |
| `src/index.css` | 重写：点阵底、卡片 / 按钮 / 输入 / 徽标 / 表格 / 进度 / 栅格 / 工具类（`.micro`、`.toolbar`、`.grid-2/3/4`、`.budget`） |
| `src/styles/layout.css` | 新增：`.app-shell` / 侧栏 `.sb-*` / 顶栏 `.topbar` / 训练顶栏 |
| `src/styles/training.css` | 新增：代码面板 `.code-*`、对话气泡 `.chat-*`、题目导航 `.qnav-*`、证据 `.evidence-*` |

### 组件
- 新增 `src/components/icons.tsx`：一套 1.75px 线性图标（替换原先 `▦ ＋ ☰ ◔ ◉` 字符图标）
- 重写：`Sidebar`（232px + 分组微标 + 左侧 2px 选中标记）、`Topbar`（面包屑 + 状态胶囊 + 刷新 + 用户块）、`AppLogo`、`PageHeader`（新增 `eyebrow`）、`StatCard`（等宽小标 + 角标「演示」）、`EmptyState`、`LoadingState`、`ErrorState`、`ConfirmDialog`
- 重写训练组件：`CodePanel`（浅色代码面板 + 窗口三点 + 行高亮 + 定位徽标）、`AdversaryChat`（气泡样式统一，去掉硬编码 `#EEF2F6`）、`TrainingProgress`（预算格）、`QuestionNavigator`、`EvidencePanel`

### 页面
- `DashboardPage` 重排：微标页头 + 欢迎区（续练/新开态）+ 4 指标 + 最近训练表 + 训练规则卡
- `HistoryPage`：筛选收进卡头（`.card-head` + `.toolbar`），状态列改用 `SessionStatusBadge`
- `SystemPage` / `AnalyticsPage` / `TrainingSetupPage` / `ReportPage`：统一页头微标、栅格类、内容宽度 1120
- `AuthLayout` / `LoginPage`：左侧品牌区改白底 + 点阵 + 光晕，右侧表单卡统一

### 验证
- `node ./node_modules/typescript/bin/tsc -b` 通过
- `npm run build` 通过：CSS 17.39 kB（gzip 4.45）、JS 343.97 kB（gzip 106.82）
- 实机截图：`shots/ui_dashboard.png`、`ui_training.png`、`ui_report.png`、`ui_history.png`、`ui_system.png`、`ui_setup.png`、`ui_login.png`、`ui_analytics.png`

### 跑起来
```powershell
cd Mine-clearance-main\frontend
npm run dev:mock      # 演示数据模式
# 或 npm run dev      # 接真实后端
```

### 2026-11-12 第二轮：缩放后的空白修正
- 训练页：代码栏改为**按实测代码宽度收缩**（`CodePanel` 新增 `onMeasure`，用 `ResizeObserver` 量 `pre.scrollWidth`），面板不再随窗口拉长；省出的宽度给右侧对抗区，三栏整体居中，超宽屏是左右等宽留白而不是单边空白。
- 开始训练 / 能力分析 / 系统状态 / 训练报告：去掉 `maxWidth: 1120` 的固定上限，卡片随窗口铺满。
