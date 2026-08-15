import { useEffect, useRef, useState } from 'react'
import { apiGet, apiPost, connectWS } from '../api.js'
import { splitReport, extractHeadings, renderMarkdown, tableToHtml } from '../markdown.js'
import { chartToOption } from '../charts.js'
import { Chart, Pipeline, LogBox, TierBadge, StatusBadge } from '../components.jsx'
import ReviewPanel from './ReviewPanel.jsx'

const RULE_LABEL = {
  financial_reconciliation: '财务勾稽',
  industry_range: '行业区间',
  time_series: '时间序列',
  multi_source_deviation: '多源偏差',
}

export default function Report({ id }) {
  const [detail, setDetail] = useState(null)
  const [logs, setLogs] = useState([])
  const [ws, setWs] = useState(null)
  const [err, setErr] = useState('')

  async function load() {
    try {
      const d = await apiGet(`/api/projects/${id}`)
      setDetail(d)
    } catch (e) {
      setErr(e.message)
    }
  }

  useEffect(() => { load() }, [id])

  // 运行中 → 连 WebSocket 收进度
  useEffect(() => {
    if (!detail) return
    const status = detail.checkpoint?.status
    if (status === 'running' || status === 'paused') {
      const ws = connectWS(id, (msg) => {
        setLogs((prev) => [...prev, ...(msg.new_logs || [])])
        if (msg.status === 'completed' || msg.status === 'failed') {
          ws.close()
          load() // 拉取完整结果
        }
      })
      setWs(ws)
      return () => ws.close()
    }
  }, [detail?.checkpoint?.status])

  async function action(path) {
    try { await apiPost(path); load() } catch (e) { setErr(e.message) }
  }

  if (err) return <div className="card">加载失败：{err}</div>
  if (!detail) return <div className="empty"><span className="spin" /> 加载中…</div>

  const ck = detail.checkpoint || {}
  const result = detail.result
  const status = ck.status
  const running = status === 'running' || status === 'paused'

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', gap: '0.8rem', marginBottom: '1rem' }}>
        <div style={{ flex: 1 }}>
          <div className="report-title" style={{ fontSize: 20 }}>
            {ck.topic || result?.topic || '调研课题'}
          </div>
          <div className="muted" style={{ fontSize: 13 }}>项目 {id}</div>
        </div>
        <StatusBadge status={status} />
      </div>

      {ck.review_stage ? (
        <ReviewPanel projectId={id} reviewStage={ck.review_stage} onDone={load} />
      ) : running ? (
        <RunningPanel detail={detail} logs={logs} onPause={() => action(`/api/projects/${id}/pause`)} onResume={() => action(`/api/projects/${id}/resume`)} onReset={() => action(`/api/projects/${id}/reset`)} />
      ) : result ? (
        <ReportBody result={result} />
      ) : (
        <div className="empty">该项目尚无报告结果。</div>
      )}
    </div>
  )
}

function RunningPanel({ detail, logs, onPause, onResume, onReset }) {
  const ck = detail.checkpoint || {}
  // 阶段状态：优先用 checkpoint 里已完成的阶段推导，日志兜底
  const stages = deriveStages(ck)
  return (
    <div>
      <div className="sec-title">多智能体流水线</div>
      <div className="card">
        <Pipeline stages={stages} />
        <div style={{ marginTop: '0.8rem', display: 'flex', gap: '0.6rem', flexWrap: 'wrap' }}>
          {ck.status === 'running' ? (
            <button className="btn" onClick={onPause}>暂停调研</button>
          ) : (
            <>
              <button className="btn primary" onClick={onResume}>继续调研</button>
              <button className="btn" onClick={onReset}>从头重跑</button>
            </>
          )}
        </div>
      </div>
      <div className="sec-title">实时日志</div>
      <LogBox entries={logs} />
    </div>
  )
}

// 从 checkpoint 的 stages 推导 6 步状态
function deriveStages(ck) {
  const order = ['architect', 'research', 'verify', 'structure', 'write', 'render']
  const st = ck.stages || {}
  return order.map((s) => {
    if (st[s]?.status === 'done') return 'done'
    return 'pending'
  })
}

function ReportBody({ result }) {
  const ai = result.ai_data || {}
  const title = ai.report_title || '调研报告'
  const core = ai.core_insights || ''
  const md = ai.markdown_report || ''
  const charts = ai.charts || []
  const tables = ai.tables || []
  const refs = ai.references || []
  const evidence = result.evidence || []
  const conflicts = result.conflicts || []
  const warnings = result.warnings || []
  const trace = result.trace || {}

  const headings = extractHeadings(md)
  const conflictClaims = new Set((conflicts || []).map((c) => c.claim))

  return (
    <div>
      <div className="report-head">
        <div className="report-title">{title}</div>
        <div className="report-meta">
          发布日期：{ai.publish_date || '—'} · 研究引擎：Eco-Research Copilot
        </div>
      </div>

      {core && (
        <div className="abstract">
          <div className="ab-label">摘要 · Core Insights</div>
          <div className="ab-text">{core}</div>
        </div>
      )}

      {headings.length > 0 && (
        <div className="toc">
          {headings.map((h, i) => <span key={i} className="toc-item">{h}</span>)}
        </div>
      )}

      {warnings.length > 0 && <WarningsPanel warnings={warnings} />}

      <div className="sec-title">正文</div>
      <div className="card report-body">
        {splitReport(md).map((part, i) => {
          if (part.kind === 'CHART') {
            const idx = part.index - 1
            const chart = charts[idx]
            const opt = chart ? chartToOption(chart) : null
            if (!chart) return null
            return (
              <div className="chart-box" key={`c${i}`}>
                {chart.title && <div className="chart-title">{chart.title}</div>}
                {opt ? <Chart option={opt} /> : <div className="muted">（图表数据缺失）</div>}
              </div>
            )
          }
          if (part.kind === 'TABLE') {
            const idx = part.index - 1
            const table = tables[idx]
            if (!table) return null
            return (
              <div key={`t${i}`}>
                {table.title && <div className="chart-title">{table.title}</div>}
                <div dangerouslySetInnerHTML={{ __html: tableToHtml(table) }} />
              </div>
            )
          }
          return <div key={`x${i}`} dangerouslySetInnerHTML={{ __html: renderMarkdown(part.text) }} />
        })}
      </div>

      {refs.length > 0 && (
        <>
          <div className="sec-title">参考文献</div>
          <div className="card">
            <ol style={{ margin: 0, paddingLeft: '1.3rem', lineHeight: 1.9, fontSize: 13.5 }}>
              {refs.map((r, i) => (
                <li key={i}>
                  {r.title}
                  {r.url ? <> — <a href={r.url} target="_blank" rel="noreferrer">{r.url}</a></> : null}
                </li>
              ))}
            </ol>
          </div>
        </>
      )}

      {evidence.length > 0 && (
        <>
          <div className="sec-title">证据溯源 · Evidence Trail</div>
          <div className="muted" style={{ fontSize: 13, marginBottom: '0.6rem' }}>每条结论绑定信源等级 / 机构 / 原文摘录 / 链接，可逐条核查。</div>
          {evidence.map((ev, i) => {
            const claim = (ev.claim || ev.excerpt || '').trim()
            const isConflict = claim && conflictClaims.has(claim)
            return (
              <div key={i} className={`ev-row ${isConflict ? 'conflict' : ''}`}>
                <div className="ev-head">
                  <b>{i + 1}.</b>
                  <span className="ev-claim">{claim || '（无主张）'}</span>
                  <TierBadge tier={ev.source_tier} />
                  {isConflict && <span className="badge danger">数据矛盾，请人工核实</span>}
                </div>
                <div className="ev-meta">
                  {ev.publisher || '未知机构'}
                  {ev.value ? ` · ${ev.value}${ev.unit || ''}` : ''}
                  {ev.period ? ` · ${ev.period}` : ''}
                  {ev.section ? ` · ${ev.section}` : ''}
                  {ev.source_url ? <> · <a href={ev.source_url} target="_blank" rel="noreferrer">{ev.source_title || '来源链接'}</a></> : ''}
                </div>
                {ev.excerpt && <div className="ev-excerpt">{ev.excerpt}</div>}
              </div>
            )
          })}
        </>
      )}

      <TracePanel trace={trace} />
    </div>
  )
}

function WarningsPanel({ warnings }) {
  return (
    <div className="card" style={{ borderColor: 'var(--gold)', marginBottom: '1rem' }}>
      <div className="sec-title" style={{ margin: '0 0 0.4rem' }}>
        🔎 投研校验预警 · {warnings.length} 项（供采信决策，不阻断）
      </div>
      {warnings.map((w, i) => (
        <div key={i} className={`warn-item ${w.level === 'verify' ? 'verify' : ''}`}>
          {w.level === 'verify' ? '🔍 待核实' : '⚠ 预警'}【{RULE_LABEL[w.rule] || w.rule}】{w.message}
          {(w.detail?.sources || []).length > 0 && (
            <div className="muted" style={{ fontSize: 12 }}>
              　↳ 来源：{(w.detail.sources || []).map((s) => `${s.title || '未署名'}（${s.tier}级）`).join('；')}
            </div>
          )}
        </div>
      ))}
    </div>
  )
}

function TracePanel({ trace }) {
  if (!trace || !Object.keys(trace).length) return null
  const order = [
    ['architect', '① 课题架构 · 框架匹配'],
    ['research_verify', '② 检索 + 代码稽核'],
    ['structure', '③ 结构化提炼'],
    ['write_audit', '④ 撰写 + 逻辑校验'],
    ['render', '⑤ 渲染排版'],
  ]
  return (
    <>
      <div className="sec-title">运行链路 · Trace</div>
      <div className="card">
        {order.map(([key, label]) => {
          const t = trace[key]
          if (!t) return null
          let summary = `${t.elapsed ?? '?'}s`
          if (key === 'architect') summary += ` · ${t.outline ?? 0} 章节 · ${t.requirements ?? 0} 必答问题`
          if (key === 'research_verify') summary += ` · ${t.rounds ?? '?'} 轮 · ${t.evidence ?? 0} 条证据 · ${t.warnings ?? 0} 项预警 · ${t.is_pass ? '通过' : '未通过'}`
          if (key === 'structure') summary += ` · ${t.charts ?? 0} 图 · ${t.tables ?? 0} 表`
          if (key === 'write_audit') summary += ` · ${t.chars ?? 0} 字`
          if (key === 'render') summary += t.docx ? ' · Word 已生成' : ''
          return (
            <div key={key} style={{ padding: '0.4rem 0', borderBottom: '1px dashed var(--border)', fontSize: 13.5 }}>
              <b>{label}</b> <span className="muted">· {summary}</span>
            </div>
          )
        })}
      </div>
    </>
  )
}
