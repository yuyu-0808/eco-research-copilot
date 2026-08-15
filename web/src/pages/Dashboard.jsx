import { useEffect, useState } from 'react'
import { apiGet } from '../api.js'
import { Kpi, StatusBadge } from '../components.jsx'

function fmtDuration(sec) {
  sec = Math.round(sec)
  if (sec < 60) return `${sec}s`
  const m = Math.floor(sec / 60)
  if (m < 60) return `${m}m ${sec % 60}s`
  const h = Math.floor(m / 60)
  return `${h}h ${m % 60}m`
}

export default function Dashboard({ go }) {
  const [data, setData] = useState(null)
  const [err, setErr] = useState('')

  useEffect(() => {
    apiGet('/api/projects')
      .then(setData)
      .catch((e) => setErr(e.message))
  }, [])

  if (err) return <div className="card">加载失败：{err}</div>
  if (!data) return <div className="empty"><span className="spin" /> 加载中…</div>

  const { projects, metrics } = data
  const m = metrics || {}

  return (
    <div>
      <div className="sec-title">工作台 · 概览</div>
      <div className="kpi-grid">
        <Kpi label="累计调研" value={m.total ?? projects.length} unit="个" />
        <Kpi label="已完成" value={m.completed ?? 0} unit="个" />
        <Kpi label="生成图表" value={m.charts ?? 0} unit="张" />
        <Kpi label="数据质检通过率" value={m.qa_rate ?? 0} unit="%" />
      </div>

      <div className="sec-title">调研项目</div>
      {projects.length === 0 ? (
        <div className="empty">还没有项目，点左侧「新建调研」开始第一个课题。</div>
      ) : (
        <div className="proj-list">
          {projects.map((p) => (
            <div className="proj-row" key={p.id}>
              <div className="proj-main">
                <div className="proj-topic">{p.topic || p.id}</div>
                <div className="proj-meta">
                  {p.relative_time || '—'} · 耗时 {fmtDuration(p.duration || 0)} · {p.n_charts} 图 · {p.n_tables} 表
                </div>
              </div>
              <StatusBadge status={p.status} />
              {p.has_result || p.has_docx ? (
                <button className="btn" onClick={() => go(`/report/${p.id}`)}>查看报告</button>
              ) : (
                <button className="btn" onClick={() => go(`/report/${p.id}`)}>查看进度</button>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
