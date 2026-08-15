import { useEffect, useState } from 'react'
import { apiGet, apiPost, apiPut, apiDelete, getToken } from '../api.js'
import { chartToOption } from '../charts.js'
import { Chart } from '../components.jsx'

const METRIC_LABEL = {
  revenue: '营业收入', net_profit: '净利润', gross_profit: '毛利', operating_cost: '营业成本',
  gross_margin: '毛利率', net_margin: '净利率', market_size: '市场规模', penetration: '渗透率',
  market_share: '市场份额', growth_rate: '增速', shipments: '出货量', capacity: '产能', price: '价格',
}

const METRIC_OPTIONS = [
  ['revenue', '营业收入'], ['net_profit', '净利润'], ['gross_profit', '毛利'],
  ['operating_cost', '营业成本'], ['gross_margin', '毛利率'], ['net_margin', '净利率'],
  ['market_size', '市场规模'], ['penetration', '渗透率'], ['market_share', '市场份额'],
  ['growth_rate', '增速'], ['shipments', '出货量'], ['capacity', '产能'], ['price', '价格'],
]

// 比例型指标（趋势图按百分比展示）
const RATIO_METRICS = new Set(['gross_margin', 'net_margin', 'penetration', 'market_share', 'growth_rate'])

const TIER_OPTIONS = ['A', 'B', 'C', 'D', 'E', 'F']

export default function Metrics() {
  const [data, setData] = useState(null)
  const [frameworks, setFrameworks] = useState([])
  const [industry, setIndustry] = useState('')
  const [year, setYear] = useState('')
  const [metricFilter, setMetricFilter] = useState('')
  const [err, setErr] = useState('')
  const [showForm, setShowForm] = useState(false)
  const [editing, setEditing] = useState(null)
  const [trend, setTrend] = useState(null)
  const [trendMetric, setTrendMetric] = useState('')

  function load() {
    const qs = new URLSearchParams()
    if (industry) qs.set('framework_key', industry)
    if (metricFilter) qs.set('metric', metricFilter)
    if (year) qs.set('year', year)
    const q = qs.toString() ? `?${qs}` : ''
    apiGet(`/api/metrics${q}`).then(setData).catch((e) => setErr(e.message))
  }

  function loadFrameworks() {
    apiGet('/api/frameworks')
      .then((d) => setFrameworks(d.frameworks || []))
      .catch(() => {})
  }

  useEffect(() => { load(); loadFrameworks() }, [])
  useEffect(() => { load() }, [industry, year, metricFilter])

  function showTrend(metric) {
    if (!industry) { setErr('请先选择行业，再看单指标趋势'); return }
    setTrendMetric(metric)
    apiGet(`/api/metrics/trend?framework_key=${encodeURIComponent(industry)}&metric=${encodeURIComponent(metric)}`)
      .then(setTrend)
      .catch((e) => setErr(e.message))
  }

  function openCreate() { setEditing(null); setShowForm(true) }
  function openEdit(row) { setEditing(row); setShowForm(true) }

  async function remove(row) {
    if (!window.confirm(`确认删除「${row.metric_label || row.metric} ${row.value}」这条指标？`)) return
    try { await apiDelete(`/api/metrics/${row.id}`); load() } catch (e) { setErr(e.message) }
  }

  if (err) return <div className="card">加载失败：{err}</div>
  if (!data) return <div className="empty"><span className="spin" /> 加载中…</div>

  const rows = data.metrics || []
  const years = [...new Set(rows.map((r) => r.year).filter(Boolean))].sort((a, b) => a - b)
  const exportQs = new URLSearchParams()
  if (industry) exportQs.set('framework_key', industry)
  exportQs.set('token', getToken())

  const trendChart = trend ? {
    type: 'line',
    labels: trend.series.map((s) => String(s.year)),
    data: trend.series.map((s) => {
      const v = s.value_norm
      return RATIO_METRICS.has(trend.metric) ? Math.round(v * 10000) / 100 : v
    }),
  } : null

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', gap: '0.8rem', marginBottom: '1rem' }}>
        <div className="sec-title" style={{ margin: 0 }}>指标库 · 数据飞轮</div>
        <div style={{ flex: 1 }} />
        <button className="btn primary" onClick={openCreate}>＋ 手动录入</button>
        <a className="btn" href={`/api/metrics/export?${exportQs.toString()}`} download>导出 Excel</a>
      </div>

      <div className="card" style={{ marginBottom: '1rem' }}>
        <div style={{ display: 'flex', gap: '0.6rem', alignItems: 'center', flexWrap: 'wrap' }}>
          <label style={{ fontSize: 13, fontWeight: 700 }}>筛选</label>
          <select value={industry} onChange={(e) => { setIndustry(e.target.value); setTrend(null) }}>
            <option value="">全部行业</option>
            {frameworks.map((f) => <option key={f.key} value={f.key}>{f.name || f.key}</option>)}
          </select>
          <select value={year} onChange={(e) => setYear(e.target.value)}>
            <option value="">全部年份</option>
            {years.map((y) => <option key={y} value={y}>{y} 年</option>)}
          </select>
          <select value={metricFilter} onChange={(e) => setMetricFilter(e.target.value)}>
            <option value="">全部指标</option>
            {METRIC_OPTIONS.map(([k, l]) => <option key={k} value={k}>{l}</option>)}
          </select>
          <span className="muted" style={{ fontSize: 13 }}>
            共 {data.count} 条沉淀指标 · 每次报告生成后自动沉淀，越用越准
          </span>
        </div>
      </div>

      {trend && trendChart && trend.series.length > 0 && (
        <div className="card" style={{ marginBottom: '1rem' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem', marginBottom: '0.4rem' }}>
            <b>{METRIC_LABEL[trend.metric] || trend.metric} 趋势</b>
            {RATIO_METRICS.has(trend.metric) && <span className="muted" style={{ fontSize: 12 }}>（单位 %）</span>}
            <button className="btn" style={{ marginLeft: 'auto', padding: '0.2rem 0.6rem', fontSize: 12 }} onClick={() => setTrend(null)}>收起</button>
          </div>
          <Chart option={chartToOption(trendChart)} height={220} />
        </div>
      )}

      {showForm && (
        <MetricForm
          frameworks={frameworks}
          editing={editing}
          onClose={() => setShowForm(false)}
          onSaved={() => { setShowForm(false); load() }}
        />
      )}

      {rows.length === 0 ? (
        <div className="empty">暂无沉淀指标。跑一次调研后通过校验的核心指标会自动沉淀，也可点「手动录入」补充。</div>
      ) : (
        <div className="card" style={{ padding: 0, overflowX: 'auto' }}>
          <table className="report-table" style={{ margin: 0 }}>
            <thead>
              <tr>
                <th>行业</th><th>指标</th><th>数值</th><th>单位</th><th>时间</th>
                <th>信源</th><th>来源</th><th>操作</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r, i) => (
                <tr key={r.id ?? i}>
                  <td>{r.framework_key || '—'}</td>
                  <td>{r.metric_label || METRIC_LABEL[r.metric] || r.metric}</td>
                  <td>{r.value}</td>
                  <td>{r.unit || '—'}</td>
                  <td>{r.period || (r.year ? `${r.year} 年` : '—')}</td>
                  <td><span className={`badge badge-grade-${(r.source_tier || 'D').toLowerCase()}`}>{r.source_tier}</span></td>
                  <td>
                    {r.source_url
                      ? <a href={r.source_url} target="_blank" rel="noreferrer">{r.source_title || r.publisher || '来源'}</a>
                      : (r.source_title || r.publisher || '—')}
                  </td>
                  <td>
                    <div style={{ display: 'flex', gap: '0.4rem', flexWrap: 'nowrap' }}>
                      <button className="btn" style={{ padding: '0.15rem 0.5rem', fontSize: 12 }} onClick={() => showTrend(r.metric)}>趋势</button>
                      <button className="btn" style={{ padding: '0.15rem 0.5rem', fontSize: 12 }} onClick={() => openEdit(r)}>编辑</button>
                      <button className="btn" style={{ padding: '0.15rem 0.5rem', fontSize: 12, color: 'var(--danger)' }} onClick={() => remove(r)}>删除</button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

function MetricForm({ frameworks, editing, onClose, onSaved }) {
  const [form, setForm] = useState(() => editing ? {
    framework_key: editing.framework_key || '',
    metric: editing.metric || '',
    value: editing.value || '',
    unit: editing.unit || '',
    period: editing.period || '',
    source_tier: editing.source_tier || 'D',
    source_title: editing.source_title || '',
    source_url: editing.source_url || '',
    publisher: editing.publisher || '',
  } : {
    framework_key: '', metric: '', value: '', unit: '', period: '',
    source_tier: 'D', source_title: '', source_url: '', publisher: '',
  })
  const [saving, setSaving] = useState(false)
  const [msg, setMsg] = useState('')

  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }))

  async function submit() {
    if (!form.framework_key || !form.metric || !form.value) {
      setMsg('行业 / 指标 / 数值为必填')
      return
    }
    setSaving(true)
    setMsg('')
    try {
      if (editing) await apiPut(`/api/metrics/${editing.id}`, form)
      else await apiPost('/api/metrics', form)
      onSaved()
    } catch (e) {
      setMsg(e.message)
      setSaving(false)
    }
  }

  return (
    <div className="card" style={{ borderColor: 'var(--brand)', marginBottom: '1rem' }}>
      <div style={{ display: 'flex', alignItems: 'center', marginBottom: '0.6rem' }}>
        <b>{editing ? '编辑指标' : '手动录入指标'}</b>
        <button className="btn" style={{ marginLeft: 'auto', padding: '0.2rem 0.6rem', fontSize: 12 }} onClick={onClose}>取消</button>
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: '0.6rem' }}>
        <div className="field" style={{ margin: 0 }}>
          <label>行业 *</label>
          <select value={form.framework_key} onChange={set('framework_key')}>
            <option value="">选择行业</option>
            {frameworks.filter((f) => f.key !== 'generic').map((f) => <option key={f.key} value={f.key}>{f.name || f.key}</option>)}
          </select>
        </div>
        <div className="field" style={{ margin: 0 }}>
          <label>指标 *</label>
          <select value={form.metric} onChange={set('metric')}>
            <option value="">选择指标</option>
            {METRIC_OPTIONS.map(([k, l]) => <option key={k} value={k}>{l}</option>)}
          </select>
        </div>
        <div className="field" style={{ margin: 0 }}>
          <label>数值 *</label>
          <input value={form.value} onChange={set('value')} placeholder="如 35% / 1.2万亿元" />
        </div>
        <div className="field" style={{ margin: 0 }}>
          <label>单位</label>
          <input value={form.unit} onChange={set('unit')} placeholder="自动识别，可覆盖" />
        </div>
        <div className="field" style={{ margin: 0 }}>
          <label>时间</label>
          <input value={form.period} onChange={set('period')} placeholder="如 2024年 / 2024Q3" />
        </div>
        <div className="field" style={{ margin: 0 }}>
          <label>信源等级</label>
          <select value={form.source_tier} onChange={set('source_tier')}>
            {TIER_OPTIONS.map((t) => <option key={t} value={t}>{t} 级</option>)}
          </select>
        </div>
        <div className="field" style={{ margin: 0 }}>
          <label>来源标题</label>
          <input value={form.source_title} onChange={set('source_title')} />
        </div>
        <div className="field" style={{ margin: 0 }}>
          <label>来源链接</label>
          <input value={form.source_url} onChange={set('source_url')} />
        </div>
        <div className="field" style={{ margin: 0 }}>
          <label>发布机构</label>
          <input value={form.publisher} onChange={set('publisher')} />
        </div>
      </div>
      <div style={{ marginTop: '0.8rem', display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
        <button className="btn primary" onClick={submit} disabled={saving}>
          {saving ? (<><span className="spin" /> 保存中…</>) : (editing ? '保存修改' : '录入指标')}
        </button>
        {msg && <span style={{ color: 'var(--danger)', fontSize: 13 }}>{msg}</span>}
      </div>
    </div>
  )
}
