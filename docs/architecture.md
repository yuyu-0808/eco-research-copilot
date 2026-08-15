# 架构设计说明

本文补充 README 之外的实现细节，供深入阅读代码前参考。

## 数据流

一次调研的完整数据流（阶段产物以粗体标出）：

1. **课题架构师（Architect）** 接收课题 → 匹配内置行研框架 → 输出 **`plan_data`**（`outline` 大纲 + `research_requirements` 证据要求）。
2. **信源研究员（Researcher）** 依据 `plan_data` + 上一轮 `feedback` 生成检索词 → 多源搜索 → 输出**带 A-F 评级的原始素材**。
3. **事实稽核官（Auditor）** 对素材做代码级证据校验 → 输出 **`verified_context`**（高纯度事实 + 来源标注）或 `feedback`（打回重搜）。
4. **交付渲染官（Renderer）** 做结构化提炼 → **`structure`**（标题 / 摘要 / 大纲 / 图表 / 表格 / 参考文献）。
5. **内容撰写师（Writer）** 分章撰写正文 → **`markdown_report`**，与逻辑稽核交叉校验。
6. **交付渲染官（Renderer）** 润色排版（保护 `[[CHART:n]]` / `[[TABLE:n]]` 占位符）→ 生成 **Word 报告**。

## Orchestrator 职责边界：纯调度者

`src/orchestrator.py` 的 `ResearchOrchestrator` 是**纯调度者，不接触任何业务内容**——
它不搜资料、不校验证据、不写正文、不排版，只负责把 5 个业务 Agent 串成一条流水线。

| 职责 | 说明 |
|------|------|
| **状态机流转** | 按固定 6 阶段推进任务，通过 `Checkpoint` 记录每阶段的完成状态与中间产物 |
| **断点续跑** | 每个阶段开头检查 `checkpoint`，已完成的阶段直接跳过（`resume=True` 时） |
| **阶段级重试** | `_with_retry` 包裹每个阶段，阶段失败自动重试 `STAGE_RETRY` 次 |
| **暂停 / 终止** | 在阶段边界与内循环轮次边界响应 `pause_requested` / `stop_requested` 信号 |
| **人工确认** | 手动模式（`REVIEW_MODE=manual`）下在「框架 → 素材 → 终稿」三处停下等待确认 |
| **质量熔断** | 严格模式下证据不达标且检索-稽核轮次耗尽，主动抛错，宁可不产出也不编造 |
| **数据透传** | 在 Agent 之间传递上下文（`plan_data` / `verified_context` / `structure`），不修改内容本身 |

**为什么这样分**：业务 Agent 只关心「把一件事做对」（搜 / 验 / 写 / 排版），
Orchestrator 只关心「何时做、做几遍、何时停」。编排层与业务层解耦后，新增 Agent、
调整流程顺序都不需要改动核心业务逻辑，扩展性更强。

## 检索-稽核内循环

```
        ┌─────────────────────────────────────┐
        │  round = 1 .. MAX_COLLECT_ROUNDS     │
        ▼                                     │
  Researcher.collect_data(plan, feedback)     │
        │                                     │
        ▼                                     │
  Auditor.verify_data(plan, raw_context)      │
        │                                     │
        ├── is_pass=true  ──▶ 跳出循环          │
        └── is_pass=false ──▶ feedback → 下一轮
```

- 若重试耗尽仍未达标且 `REQUIRE_STRICT_EVIDENCE=True`，**强制熔断**并抛错。
- 若宽容模式（`False`），跳过拦截继续分析，但会在上下文中标注「证据不充分」。

## 撰写-稽核交叉循环

正文分章生成后，事实稽核官对每章做**逻辑校验**（论据溯源 + 逻辑矛盾排查），争议打回内容撰写师重写，共 `WRITE_AUDIT_ROUNDS` 轮。

## 防长文截断：双模式正文

LLM 长输出易被网关截断（导致后半章节缺失），据此设计两种正文生成模式：

- **standard**：一次性生成全文（1500–2000 字），快、省调用。
- **deep**：按大纲**分章生成**（每章一次请求，400–600 字），更充实、更稳定，但调用次数更多、更慢。

`Config.REPORT_MODE` 控制，前端可在「新建调研 → 高级设置」切换。

## 图表与溯源

- 图表由 `structure.charts`（`type / labels / data`）驱动，前端用 Vega-Lite 渲染，Word 用 QuickChart 生成静态图。
- 正文用 `[[CHART:n]]` / `[[TABLE:n]]` 占位符标记插图位置，渲染时**就地插图**；未被引用的图表兜底追加到「附：补充数据」。
- 参考文献仅来自 `verified_context` 中真实出现的来源，正文用 `[n]` 编号引用，严禁编造。

## 目录职责

| 目录 | 职责 |
|------|------|
| `src/orchestrator.py` | 编排多智能体 + 检索-稽核内循环 + 撰写-稽核交叉循环 |
| `src/agents/` | 各智能体的 prompt 与调用逻辑 |
| `src/tools/` | 搜索、Word 生成等可复用工具 |
| `src/ui/` | 前端辅助：项目扫描、指标计算、图表渲染 |
| `src/utils/` | 配置、日志、LLM 调用、框架引擎、证据模型、代码校验器、数值归一化、信源评级 |
