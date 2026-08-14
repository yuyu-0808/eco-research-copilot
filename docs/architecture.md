# 架构设计说明

本文补充 README 之外的实现细节，供深入阅读代码前参考。

## 数据流

一次调研的完整数据流（阶段产物以粗体标出）：

1. **Planner** 接收课题 → 输出 **`plan_data`**（`outline` 大纲 + `research_requirements` 质量门禁清单）。
2. **Scraper** 依据 `plan_data` + 上一轮 `feedback` 生成检索词 → 多源搜索 → 输出**原始素材**。
3. **Verifier** 对原始素材「淘金」→ 输出 **`verified_context`**（高纯度事实 + 来源标注）或 `feedback`（打回）。
4. **Analyst** 对 `verified_context` 做结构化提炼 → **`ai_data`**（标题 / 摘要 / 大纲 / 图表 / 表格 / 参考文献 / markdown 正文）。
5. **Formatter** 润色 `ai_data.markdown_report`（保护 `[[CHART:n]]` / `[[TABLE:n]]` 占位符）→ 生成 **Word 报告**。

## 采集-质检内循环

```
        ┌─────────────────────────────────────┐
        │  round = 1 .. MAX_COLLECT_ROUNDS     │
        ▼                                     │
  Scraper.collect_data(plan, feedback)        │
        │                                     │
        ▼                                     │
  Verifier.verify_data(plan, raw_context)     │
        │                                     │
        ├── is_pass=true  ──▶ 跳出循环          │
        └── is_pass=false ──▶ feedback → 下一轮
```

- 若重试耗尽仍未达标且 `REQUIRE_STRICT_EVIDENCE=True`，**强制熔断**并抛错。
- 若宽容模式（`False`），跳过拦截继续分析，但会在上下文中标注「证据不充分」。

## 防长文截断：双模式正文

LLM 长输出易被网关截断（导致后半章节缺失），据此设计两种正文生成模式：

- **standard**：一次性生成全文（1500–2000 字），快、省调用。
- **deep**：按大纲**分章生成**（每章一次请求，400–600 字），更充实、更稳定，但调用次数更多、更慢。

`Config.REPORT_MODE` 控制，前端可在「新建调研 → 高级设置」切换。

## 图表与溯源

- 图表由 `ai_data.charts`（`type / labels / data`）驱动，前端用 Vega-Lite 渲染，Word 用 QuickChart 生成静态图。
- 正文用 `[[CHART:n]]` / `[[TABLE:n]]` 占位符标记插图位置，Formatter 排版时**就地插图**；未被引用的图表兜底追加到「附：补充数据」。
- 参考文献仅来自 `verified_context` 中真实出现的来源，正文用 `[n]` 编号引用，严禁编造。

## 目录职责

| 目录 | 职责 |
|------|------|
| `src/orchestrator.py` | 编排多智能体 + 采集-质检内循环 |
| `src/agents/` | 各智能体的 prompt 与调用逻辑 |
| `src/tools/` | 搜索、Word 生成等可复用工具 |
| `src/ui/` | 前端辅助：项目扫描、指标计算、图表渲染 |
| `src/utils/` | 配置、日志、LLM 调用（含 JSON 修复 / 重试 / 限流） |
