# Streamlit → FastAPI + React 迁移方案

> 目标：为了支撑 P0-1（异步后台任务）和 P0-3（拖拽编辑检查点），把「壳」从 Streamlit 换成 FastAPI + React。**核心逻辑 `src/` 零改动复用。**

---

## 一、结论与原则

| 原则 | 说明 |
|------|------|
| 核心逻辑零改动 | `src/orchestrator.py`、`src/agents/`、`src/utils/` 全部复用，只换 `main.py` 这一层 |
| 数据格式不变 | `checkpoint.json`、`projects/` 目录结构不变，两个前端能读同一份状态 |
| 双轨并行可回滚 | 迁移期间 Streamlit 保留，FastAPI 跑通后再删 `main.py` |
| 顺带落地 P0-1/P0-3 | 异步队列、拖拽编辑在 FastAPI + React 里天然能做，不额外返工 |

---

## 二、目标架构

```
React 前端 (Vite)           FastAPI 后端              核心逻辑（复用，零改动）
┌─────────────────┐        ┌──────────────────┐      ┌────────────────────────┐
│  工作台 / 新建   │  HTTP  │  api/             │ 调用 │  src/orchestrator.py    │
│  报告 / 证据溯源 │ ─────▶ │    projects.py    │────▶│  src/agents/*.py        │
│  拖拽编辑检查点  │        │    research.py    │      │  src/utils/validator.py │
│                 │  WS    │    review.py      │      │  src/utils/checkpoint.py│
│  实时进度/日志   │ ◀───── │  ws.py (WebSocket)│ ◀──  │  (state.json 读写)      │
└─────────────────┘        │  workers/ (队列)  │      └────────────────────────┘
                           └──────────────────┘
                                     │
                                     ▼
                              projects/ 运行时产物（不变）
```

---

## 三、新目录结构

```
eco-research-copilot/
├── src/                    # 现有核心逻辑，零改动
├── server/                 # 新增：FastAPI 后端
│   ├── main.py             # FastAPI 入口 + CORS + 静态托管
│   ├── api/
│   │   ├── projects.py     # 项目 CRUD + 列表 + 详情
│   │   ├── research.py     # 任务提交/暂停/续跑/复位/结果
│   │   ├── review.py       # 三阶段确认（可编辑）
│   │   └── settings.py     # 配置读写
│   ├── workers/
│   │   ├── queue.py        # 后台任务队列（APScheduler）
│   │   └── runner.py       # 执行器：调 orchestrator.run()
│   └── ws.py               # WebSocket 进度推送
├── web/                    # 新增：React 前端（Vite）
│   ├── src/
│   │   ├── pages/          # Dashboard / NewResearch / Report / Settings
│   │   ├── components/     # 拖拽 / 信源卡片 / 图表 / 溯源面板
│   │   ├── api/            # fetch 封装 + WebSocket client
│   │   └── store/          # 轻量状态（zustand）
│   └── package.json
├── projects/               # 运行时产物（不变，历史项目兼容）
├── main.py                 # 旧 Streamlit，保留到迁移完成
└── .env.example
```

---

## 四、API 设计

### 4.1 项目

| 方法 | 路径 | 说明 | 对应现有逻辑 |
|------|------|------|------|
| GET | `/api/projects` | 项目列表（状态/耗时/图表数/KPI） | `main.py` 的 `_scan_projects` |
| POST | `/api/projects` | 创建项目（topic + 配置） | 新建调研表单 |
| GET | `/api/projects/{id}` | 项目详情（读 `checkpoint.json`） | `Checkpoint.load()` |
| DELETE | `/api/projects/{id}` | 删除项目目录 | — |

### 4.2 调研任务

| 方法 | 路径 | 说明 | 对应现有逻辑 |
|------|------|------|------|
| POST | `/api/projects/{id}/run` | 提交任务到队列 | `_start_worker` → 后台线程 |
| POST | `/api/projects/{id}/pause` | 请求暂停 | `Checkpoint.request_pause()` |
| POST | `/api/projects/{id}/resume` | 从断点续跑 | `Orchestrator(resume=True).run()` |
| POST | `/api/projects/{id}/reset` | 从某阶段复位重跑 | `Checkpoint.reset_from(stage)` |
| GET | `/api/projects/{id}/result` | 报告数据（evidence/conflicts/reasons/trace/docx） | `load_result` + `_finalize_completed` |

### 4.3 三阶段确认（P0-3 可编辑版）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/projects/{id}/review` | 当前确认点 + 可编辑数据 |
| PUT | `/api/projects/{id}/review/framework` | 保存框架编辑（章节增删/排序/门槛） |
| PUT | `/api/projects/{id}/review/materials` | 保存素材编辑（增删信源/调评级/标记必采） |
| PUT | `/api/projects/{id}/review/draft` | 终稿打回指定章节 + 修改意见 |
| POST | `/api/projects/{id}/review/confirm` | 确认通过 → `Checkpoint.clear_review()` + resume |

### 4.4 配置

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/settings` | 读配置（`Config` 类属性） |
| PUT | `/api/settings` | 写 `.env`（等价现有设置页） |

### 4.5 实时推送

| 通道 | 路径 | 说明 |
|------|------|------|
| WS | `/ws/projects/{id}` | 推送：阶段切换、日志行、Token 消耗、状态变化 |

> WebSocket 消息直接读 `AgentLogger` 写进项目目录的日志文件 + `checkpoint.json`，无需改动核心逻辑。

---

## 五、后台任务与队列选型

**推荐 APScheduler（进程内调度），不推荐 RQ + Redis。**

理由：
- 个人/单用户项目，无需分布式队列；Redis 在 Windows 上部署麻烦。
- 「关闭页面后任务继续跑」的关键是**后台线程 + checkpoint 文件持久化**，而非 Redis——`orchestrator.run()` 本就在独立线程跑，`checkpoint.json` 已经是断点续跑的基础。
- 队列用 APScheduler 管理任务生命周期（提交/取消/状态），执行器 `runner.py` 只做一件事：`orchestrator = ResearchOrchestrator(project_id, resume); orchestrator.run(topic)`。

```
POST /run ──▶ APScheduler 入队 ──▶ runner 线程跑 orchestrator
                    │                        │
                    │◀── 轮询 checkpoint.json ──┤（阶段/状态/日志）
                    ▼                        ▼
               WS 推给前端              projects/{id}/
```

---

## 六、与现有 `src/` 的对接点

| 现有模块 | 迁移后如何用 | 改动 |
|------|------|------|
| `ResearchOrchestrator(project_name, resume)` | `runner.py` 直接实例化调用 `.run(topic)` | 零改动 |
| `Checkpoint.load()/save()` | API 层读状态、前端展示 | 零改动 |
| `Checkpoint.request_pause()/clear_pause()` | 对应 pause/resume API | 零改动 |
| `Checkpoint.set_review()/clear_review()/reset_from()` | 对应 review/confirm/reset API | 零改动 |
| `AgentLogger.log_event()` | 日志落盘，后端读出来推 WS | 零改动 |
| `Config` | settings API 读写 `.env` | 零改动 |
| `main.py` 的 UI 逻辑 | 拆成 API + React 组件 | **重写（唯一大工程）** |

---

## 七、迁移步骤（分阶段，可随时回滚）

| 阶段 | 内容 | 产出 | 依赖 |
|------|------|------|------|
| **A** | P0-2 投研证据校验（纯后端，`validator` 扩展） | 4 个校验规则 | 无，先做不阻塞 |
| **B** | 搭 FastAPI 骨架：API + 调 orchestrator + WS + checkpoint 读写 | `server/` 可跑，Swagger 验证 | A |
| **C** | React 前端骨架：工作台 + 新建 + 报告页，对齐现有功能 | `web/` 可跑 | B |
| **D** | P0-1 异步队列（APScheduler 入队/状态）+ P0-3 拖拽编辑检查点 | 核心补强 | C |
| **E** | 功能对齐后删除 `main.py` + Streamlit 依赖 | 收尾 | D |

> 每阶段结束都可验证、可回退到 Streamlit；`checkpoint.json` 格式不变，两边共享同一份项目数据。

---

## 八、风险与注意

1. **迁移期双轨并行**：Streamlit 和 FastAPI 都读同一 `projects/`，不要在两边同时跑同一项目。
2. **checkpoint.json 格式稳定**：迁移不引入新字段（P0-1 若加「任务队列状态」字段，需向后兼容，旧项目 load 时要 `setdefault`）。
3. **WebSocket 断线重连**：前端要处理断线重连 + 重连后拉全量状态（读 checkpoint）。
4. **ECharts 红涨绿跌**：图表从 Vega-Lite 换 ECharts 时，正增长=红、负增长=绿（A 股习惯），与现有配色约定一致。
5. **前端人力**：你定位产品经理，React 前端可由我实现，你聚焦业务逻辑验收。

---

## 附：当前 P0 排序（已确认）

1. **P0-2 投研证据校验**（纯后端，最先做）
2. **P0-1 任务编排**（异步队列，随 FastAPI 迁移落地）
3. **P0-3 人机协同产品化**（拖拽编辑，在 React 里做）
4. ~~P0-4 材料中心~~（砍掉：撞车竞品 + 重依赖）
