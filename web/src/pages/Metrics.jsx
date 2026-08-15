import { useEffect, useState } from 'react'
import { apiGet, getToken } from '../api.js'

const METRIC_LABEL = {
  revenue: '营业收入', net_profit: '净利润', gross_profit: '毛利', operating_cost: '营业成本',
  gross_margin: '毛利率', net_margin: '净利率', market_size: '市场规模', penetration: '渗透率',
  market_share: '市场份额', growth_rate: '增速', shipments: '出货量', capacity: '产能', price: '价格',
}

export default function Metrics() {
  const [data, setData] = useState(null)
  const [industry, setIndustry] = useState('')
  const [err, setErr] = useState('')

  function load(key = '') {
    const q = key ? `?framework_key=${encodeURIComponent(key)}` : ''
    apiGet(`/api/metrics${q}`).then(setData).catch((e) => setErr(e.message))
  }
  useEffect(() => { load('') }, [])

  if (err) return <div className="card">加载失败：{err}</div>
  if (!data) return <div className="empty"><span className="spin" /> 加载中…</div>

  const rows = data.metrics || []
  const exportQs = new URLSearchParams()
  if (industry) exportQs.set('framework_key', industry)
  exportQs.set('token', getToken())

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', gap: '0.8rem', marginBottom: '1rem' }}>
        <div className="sec-title" style={{ margin: 0 }}>指标库 · 数据飞轮</div>
        <div style={{ flex: 1 }} />
        <a className="btn" href={`/api/metrics/export?${exportQs.toString()}`} download>
          导出 Excel
        </a>
      </div>

      <div className="card" style={{ marginBottom: '1rem' }}>
        <div style={{ display: 'flex', gap: '0.6rem', alignItems: 'center', flexWrap: 'wrap' }}>
          <label style={{ fontSize: 13, fontWeight: 700 }}>行业筛选</label>
          <select value={industry} onChange={(e) => { setIndustry(e.target.value); load(e.target.value) }}>
            <option value="">全部行业</option>
            {(data.industries || []).map((k) => <option key={k} value={k}>{k}</option>)}
          </select>
          <span className="muted" style={{ fontSize: 13 }}>
            共 {data.count} 条沉淀指标 · 每次报告生成后自动沉淀，越用越准
          </span>
        </div>
      </div>

      {rows.length === 0 ? (
        <div className="empty">暂无沉淀指标。跑一次调研后，通过校验的核心指标会自动沉淀到这里。</div>
      ) : (
        <div className="card" style={{ padding: 0, overflowX: 'auto' }}>
          <table className="report-table" style={{ margin: 0 }}>
            <thead>
              <tr>
                <th>行业</th><th>指标</th><th>数值</th><th>单位</th><th>时间</th>
                <th>信源</th><th>来源</th><th>沉淀时间</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r, i) => (
                <tr key={i}>
                  <td>{r.framework_key || '—'}</td>
                  <td>{r.metric_label || METRIC_LABEL[r.metric] || r.metric}</td>
                  <td>{r.value}</td>
                  <td>{r.unit || '—'}</td>
                  <td>{r.period || '—'}</td>
                  <td><span className={`badge badge-grade-${(r.source_tier || 'D').toLowerCase()}`}>{r.source_tier}</span></td>
                  <td>
                    {r.source_url
                      ? <a href={r.source_url} target="_blank" rel="noreferrer">{r.source_title || r.publisher || '来源'}</a>
                      : (r.source_title || r.publisher || '—')}
                  </td>
                  <td>{r.saved_at || '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
