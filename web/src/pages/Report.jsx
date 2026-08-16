import { useEffect, useMemo, useRef, useState } from 'react'
import { apiGet, apiPost, connectWS, getToken } from '../api.js'
import { splitReport, extractHeadings, renderMarkdown, tableToHtml } from '../markdown.js'
import { chartToOption } from '../charts.js'
import { Chart, Pipeline, LogBox, TierBadge, StatusBadge } from '../components.jsx'
import ReviewPanel from './ReviewPanel.jsx'

const RULE_LABEL = {
  financial_reconciliation: '财务勾稽',
  industry_range: '行业区间',
  time_series: '时间序列',
  multi_source_deviation: '多源偏差',
  historical_cross: '历史交叉验证',
}

// 质检报告规则的固定展示顺序（其余自定义规则追加在后）
const RULE_ORDER = [
  'financial_reconciliation',
  'industry_range',
  'time_series',
  'multi_source_deviation',
  'historical_cross',
]

export default function Report({ id }) {
  const [detail, setDetail] = useState(null)
  const [logs, setLogs] = useState([])
  const [err, setErr] = useState('')
  const [toast, setToast] = useState('')

  async function load() {
    try {
      const d = await apiGet(`/api/projects/${id}`)
      setDetail(d)
    } catch (e) {
      setErr(e.message)
    }
  }

  useEffect(() => { load() }, [id])

  // 进入页面即连 WebSocket（不依赖 status，解决新建项目时 checkpoint 尚未就绪）
  // 每次推送都刷新 detail，让进度条/状态/按钮随 checkpoint 实时更新（修进度条卡死 + 无继续按钮）
  useEffect(() => {
    const ws = connectWS(id, (msg) => {
      setLogs((prev) => [...prev, ...(msg.new_logs || [])])
      load()
      if (msg.status === 'completed' || msg.status === 'failed') {
        ws.close()
      }
    })
    return () => ws.close()
  }, [id])

  function flash(msg) {
    setToast(msg)
    setTimeout(() => setToast(''), 3000)
  }

  async function action(path, notice) {
    try {
      await apiPost(path)
      if (notice) flash(notice)
      load()
    } catch (e) { setErr(e.message) }
  }

  if (err) return <div className="card">加载失败：{err}</div>
  if (!detail) return <div className="empty"><span className="spin" /> 加载中…</div>

  const ck = detail.checkpoint || {}
  const result = detail.result
  const status = ck.status
  // 用 detail.running（后端 queue.is_running）兜底，避免 ck.status 为空时误判
  const running = detail.running || status === 'running' || status === 'paused'

  // 启动中：项目刚创建，orchestrator.run 异步入队，checkpoint 还没写完
  if (!ck.status && !result && !detail.running) {
    return <div className="empty"><span className="spin" /> 启动中…</div>
  }

  return (
    <div>
      {toast && (
        <div style={{ position: 'fixed', top: 80, right: 20, zIndex: 1000, background: 'var(--brand)', color: '#fff', padding: '0.6rem 1rem', borderRadius: 8, boxShadow: '0 4px 16px rgba(0,0,0,.15)', fontSize: 13 }}>
          {toast}
        </div>
      )}
      {/* 顶部悬浮操作栏 */}
      <div className="report-toolbar">
        <div style={{ flex: 1, minWidth: 0 }}>
          <div className="report-title" style={{ fontSize: 18 }}>
            {ck.topic || result?.topic || '调研课题'}
          </div>
          <div className="muted" style={{ fontSize: 12 }}>项目 {id}</div>
        </div>
        {result && !running && (
          <div style={{ display: 'flex', gap: '0.4rem', flexWrap: 'wrap' }}>
            {result.docx_path && (
              <a className="btn primary" href={`/api/projects/${id}/export/docx?token=${encodeURIComponent(getToken())}`} download>导出 Word</a>
            )}
            <a className="btn" href={`/api/projects/${id}/export/pdf?token=${encodeURIComponent(getToken())}`} download>导出 PDF</a>
            <a className="btn" href={`/api/projects/${id}/export/markdown?token=${encodeURIComponent(getToken())}`} download>导出 Markdown</a>
          </div>
        )}
        <StatusBadge status={status} />
      </div>

      {ck.review_stage ? (
        <ReviewPanel projectId={id} reviewStage={ck.review_stage} onDone={load} />
      ) : running ? (
        <RunningPanel detail={detail} logs={logs}
          onPause={() => action(`/api/projects/${id}/pause`, '已请求暂停，任务将在当前步骤完成后停下')}
          onResume={() => action(`/api/projects/${id}/resume`, '已继续')}
          onReset={() => action(`/api/projects/${id}/reset`, '已从头重跑')}
          onStop={() => action(`/api/projects/${id}/stop`, '已请求终止')} />
      ) : result ? (
        <ReportBody result={result} />
      ) : status === 'stopped' ? (
        <div className="card" style={{ borderColor: 'var(--danger)', textAlign: 'center' }}>
          <div style={{ fontSize: 15, fontWeight: 700, color: 'var(--danger)', marginBottom: '0.4rem' }}>🛑 任务已终止</div>
          <div className="muted" style={{ fontSize: 13, marginBottom: '0.8rem' }}>进度已保存，可从头重跑或从某阶段续跑。</div>
          <div style={{ display: 'flex', gap: '0.6rem', justifyContent: 'center' }}>
            <button className="btn primary" onClick={() => action(`/api/projects/${id}/resume`)}>从断点续跑</button>
            <button className="btn" onClick={() => action(`/api/projects/${id}/reset`)}>从头重跑</button>
          </div>
        </div>
      ) : (
        <div className="empty">该项目尚无报告结果。</div>
      )}
    </div>
  )
}

function RunningPanel({ detail, logs, onPause, onResume, onReset, onStop }) {
  const ck = detail.checkpoint || {}
  const stages = deriveStages(ck)
  const doneCount = stages.filter((s) => s === 'done').length
  const progress = Math.round((doneCount / stages.length) * 100)
  return (
    <div>
      <div className="sec-title">多智能体流水线</div>
      <div className="card">
        <Pipeline stages={stages} />
        <div style={{ marginTop: '0.8rem' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, color: 'var(--muted)', marginBottom: '0.3rem' }}>
            <span>总进度</span>
            <span>{doneCount}/{stages.length} 阶段 · {progress}%</span>
          </div>
          <div style={{ height: 8, background: 'var(--border)', borderRadius: 999, overflow: 'hidden' }}>
            <div style={{ width: `${progress}%`, height: '100%', background: 'var(--brand)', transition: 'width .4s var(--ease)' }} />
          </div>
        </div>
        <div style={{ marginTop: '0.8rem', display: 'flex', gap: '0.6rem', flexWrap: 'wrap' }}>
          {ck.status === 'running' ? (
            <>
              <button className="btn" onClick={onPause}>暂停调研</button>
              <button className="btn" onClick={onStop} style={{ color: 'var(--danger)', borderColor: 'var(--danger)' }}>终止任务</button>
            </>
          ) : (
            <>
              <button className="btn primary" onClick={onResume}>继续调研</button>
              <button className="btn" onClick={onReset}>从头重跑</button>
              <button className="btn" onClick={onStop} style={{ color: 'var(--danger)', borderColor: 'var(--danger)' }}>终止任务</button>
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
  const checks = result.checks || {}
  const trace = result.trace || {}

  const headings = extractHeadings(md)
  const conflictClaims = new Set((conflicts || []).map((c) => c.claim))
  const [activeRef, setActiveRef] = useState(null)
  const bodyRef = useRef(null)

  // 给 ## 标题加锚点 id（与左侧目录一一对应）；缓存避免点击引用时全量重算
  const anchoredMd = useMemo(() => {
    let hCounter = 0
    return md.replace(/^##\s+(.+)$/gm, (m, text) => `## <a id="sec-${hCounter++}"></a>${text}`)
  }, [md])

  // 切分正文并按需预渲染 HTML，避免每次点击引用都重新 marked.parse 全文
  const parts = useMemo(
    () => splitReport(anchoredMd).map((part) => ({
      ...part,
      html: part.kind === 'text' ? renderMarkdown(part.text) : null,
    })),
    [anchoredMd],
  )

  // 引用标号点击 → 弹出信源详情
  useEffect(() => {
    const el = bodyRef.current
    if (!el) return
    const onClick = (e) => {
      const cite = e.target.closest('.ref-cite')
      if (!cite) return
      const n = parseInt(cite.dataset.ref, 10)
      const ref = refs[n - 1]
      setActiveRef(ref ? { n, ref } : null)
    }
    el.addEventListener('click', onClick)
    return () => el.removeEventListener('click', onClick)
  }, [refs])

  const scrollTo = (i) => {
    document.getElementById(`sec-${i}`)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }

  return (
    <div className="report-layout">
      {headings.length > 0 && (
        <aside className="report-nav">
          <div className="report-nav-title">目录</div>
          {headings.map((h, i) => (
            <div key={i} className="report-nav-item" onClick={() => scrollTo(i)}>{h}</div>
          ))}
        </aside>
      )}

      <div className="report-content">
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

        <QAPanel checks={checks} warnings={warnings} conflicts={conflicts} />

        <div className="sec-title">正文</div>
        <div className="card report-body" ref={bodyRef}>
          {parts.map((part, i) => {
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
            return <div key={`x${i}`} dangerouslySetInnerHTML={{ __html: part.html }} />
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

      {/* 引用溯源浮层 */}
      {activeRef && <RefPopover data={activeRef} onClose={() => setActiveRef(null)} />}
    </div>
  )
}

// 引用溯源浮层：点击正文 [n] 后弹出对应信源详情
function RefPopover({ data, onClose }) {
  const { n, ref } = data
  return (
    <div className="ref-popover-mask" onClick={onClose}>
      <div className="ref-popover" onClick={(e) => e.stopPropagation()}>
        <div className="ref-popover-head">
          <span className="badge brand">信源 [{n}]</span>
          <button className="btn" style={{ padding: '0.1rem 0.5rem', fontSize: 12, marginLeft: 'auto' }} onClick={onClose}>✕</button>
        </div>
        <div className="ref-popover-title">{ref.title || '（未署名）'}</div>
        {ref.url && (
          <a className="ref-popover-url" href={ref.url} target="_blank" rel="noreferrer">{ref.url}</a>
        )}
      </div>
    </div>
  )
}

/* ---------------- 质检报告面板：分规则校验结果 + 数值矛盾 ---------------- */

function fmtNum(v) {
  if (v === undefined || v === null || v === '') return '—'
  if (typeof v === 'number') {
    if (!isFinite(v)) return String(v)
    if (Math.abs(v) >= 10000) return v.toLocaleString('zh-CN', { maximumFractionDigits: 0 })
    return String(Math.round(v * 100) / 100)
  }
  return String(v)
}

function buildGroups(checks, warnings) {
  const groups = []
  const push = (key, items) => {
    if (items && items.length > 0) groups.push({ key, label: RULE_LABEL[key] || key, items })
  }
  if (checks && Object.keys(checks).length > 0) {
    RULE_ORDER.forEach((key) => push(key, checks[key]))
    Object.keys(checks).forEach((key) => {
      if (!RULE_ORDER.includes(key)) push(key, checks[key])
    })
  } else if (warnings && warnings.length > 0) {
    const byRule = {}
    warnings.forEach((w) => { (byRule[w.rule || 'unknown'] = byRule[w.rule || 'unknown'] || []).push(w) })
    Object.entries(byRule).forEach(([key, items]) => push(key, items))
  }
  return groups
}

function DetailExtra({ issue }) {
  const d = issue.detail || {}
  switch (issue.rule) {
    case 'financial_reconciliation':
      return (
        <span className="muted" style={{ fontSize: 12 }}>
          　↳ 勾稽预期 <span className="num">{fmtNum(d.expected)}</span>，实际记录 <span className="num danger">{fmtNum(d.actual)}</span>
        </span>
      )
    case 'industry_range':
      return (
        <span className="muted" style={{ fontSize: 12 }}>
          　↳ 异常值 <span className="num danger">{fmtNum(d.value)}%</span>，常识区间 {fmtNum(d.range?.[0])} ~ {fmtNum(d.range?.[1])}
        </span>
      )
    case 'time_series':
      return (
        <span className="muted" style={{ fontSize: 12 }}>
          　↳ {fmtNum(d.from?.year)} 年 <span className="num">{fmtNum(d.from?.value)}</span> → {fmtNum(d.to?.year)} 年 <span className="num danger">{fmtNum(d.to?.value)}</span>
        </span>
      )
    case 'multi_source_deviation':
      return (
        <span className="muted" style={{ fontSize: 12 }}>
          　↳ 多源区间 <span className="num danger">{fmtNum(d.min)}</span> ~ <span className="num danger">{fmtNum(d.max)}</span>
          {d.sources?.length > 0 && (
            <>　来源：{d.sources.map((s) => `${s.title || '未署名'}（${s.tier || '?'}级）`).join('；')}</>
          )}
        </span>
      )
    case 'historical_cross':
      return (
        <span className="muted" style={{ fontSize: 12 }}>
          　↳ 当前 <span className="num danger">{d.current?.value || '—'}</span> vs 历史 <span className="num">{d.historical?.value || '—'}</span>
          {d.historical?.source_tier ? `（历史为 ${d.historical.source_tier} 级信源）` : ''}
        </span>
      )
    default:
      return null
  }
}

function QAPanel({ checks, warnings, conflicts }) {
  const groups = buildGroups(checks, warnings)
  const allIssues = groups.flatMap((g) => g.items)
  const warnCount = allIssues.filter((i) => i.level !== 'verify').length
  const verifyCount = allIssues.filter((i) => i.level === 'verify').length
  const conflictCount = (conflicts || []).length

  if (allIssues.length === 0 && conflictCount === 0) {
    return (
      <div className="card" style={{ borderColor: 'var(--success)', marginBottom: '1rem' }}>
        <div className="sec-title" style={{ margin: '0 0 0.4rem' }}>🛡 质检报告 · Quality Report</div>
        <div style={{ fontSize: 13.5, color: 'var(--success)', fontWeight: 600 }}>
          ✓ 全部校验通过：财务勾稽 / 行业区间 / 时间序列 / 多源偏差 / 历史交叉验证均无异常，数值口径一致。
        </div>
      </div>
    )
  }

  return (
    <>
      <div className="sec-title">🛡 质检报告 · Quality Report</div>
      <div className="card" style={{ marginBottom: '1rem' }}>
        <div className="qa-summary">
          {warnCount > 0 && <span className="badge danger">⚠ 预警 {warnCount} 项</span>}
          {verifyCount > 0 && <span className="badge part">🔍 待核实 {verifyCount} 项</span>}
          {conflictCount > 0 && <span className="badge danger">✗ 数值矛盾 {conflictCount} 处</span>}
        </div>

        {groups.map((g) => (
          <div key={g.key} className="qa-group">
            <div className="qa-group-title">{g.label} <span className="muted">· {g.items.length} 项</span></div>
            {g.items.map((it, i) => (
              <div key={i} className={`warn-item ${it.level === 'verify' ? 'verify' : ''}`}>
                {it.level === 'verify' ? '🔍 待核实' : '⚠ 预警'}　{it.message}
                <div><DetailExtra issue={it} /></div>
              </div>
            ))}
          </div>
        ))}

        {conflictCount > 0 && (
          <div className="qa-group">
            <div className="qa-group-title" style={{ color: 'var(--danger)' }}>数值矛盾 · {conflictCount} 处</div>
            {conflicts.map((c, i) => (
              <div key={i} className="ev-row conflict" style={{ padding: '0.6rem 0.8rem' }}>
                <div style={{ fontSize: 13 }}>
                  <span className="num danger">{c.claim || '—'}</span>
                  <span className="muted" style={{ marginLeft: '0.5rem' }}>{c.section || ''}</span>
                </div>
                <div className="muted" style={{ fontSize: 12, marginTop: '0.2rem' }}>
                  冲突值：{((c.values || []).map((v) => <span key={v} className="num danger" style={{ marginRight: '0.5rem' }}>{v}</span>))}
                  {c.sources?.length > 0 && <>　来源：{c.sources.map((s) => `${s.title || '未署名'}（${s.tier || '?'}级）`).join('；')}</>}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </>
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
