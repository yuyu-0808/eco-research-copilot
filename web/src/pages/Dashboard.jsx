import { useEffect, useState } from 'react'
import { apiGet, apiPost } from '../api.js'
import { Kpi, StatusBadge } from '../components.jsx'

function fmtDuration(sec) {
  sec = Math.round(sec)
  if (sec < 60) return `${sec}s`
  const m = Math.floor(sec / 60)
  if (m < 60) return `${m}m ${sec % 60}s`
  const h = Math.floor(m / 60)
  return `${h}h ${m % 60}m`
}

function fmtToken(n) {
  if (!n) return '0'
  if (n >= 10000) return `${(n / 10000).toFixed(1)}万`
  return `${n}`
}

export default function Dashboard({ go }) {
  const [data, setData] = useState(null)
  const [stats, setStats] = useState(null)
  const [err, setErr] = useState('')
  const [showArchived, setShowArchived] = useState(false)

  function load() {
    apiGet(`/api/projects${showArchived ? '?include_archived=1' : ''}`)
      .then(setData)
      .catch((e) => setErr(e.message))
  }
  useEffect(() => {
    load()
    apiGet('/api/stats').then(setStats).catch(() => {})
  }, [showArchived])

  async function act(path, body) {
    try {
      await apiPost(path, body)
      load()
    } catch (e) {
      setErr(e.message)
    }
  }

  async function rename(p) {
    const name = window.prompt('新的项目名称：', p.topic)
    if (name && name.trim()) {
      await act(`/api/projects/${p.id}/rename`, { topic: name.trim() })
    }
  }

  async function retry(p) {
    await act(`/api/projects/${p.id}/retry`)
    go(`/report/${p.id}`)
  }

  if (err) return <div className="card">加载失败：{err}</div>
  if (!data) return <div className="empty"><span className="spin" /> 加载中…</div>

  const { projects } = data
  const m = data.metrics || {}
  const s = stats || {}

  return (
    <div>
      <div className="sec-title">工作台 · 概览</div>
      <div className="kpi-grid">
        <Kpi label="累计调研" value={m.total ?? projects.length} unit="个" />
        <Kpi label="已完成" value={m.completed ?? 0} unit="个" />
        <Kpi label="生成图表" value={m.charts ?? 0} unit="张" />
        <Kpi label="数据质检通过率" value={m.qa_rate ?? 0} unit="%" />
      </div>

      <div className="sec-title">运行统计</div>
      <div className="kpi-grid">
        <Kpi label="任务成功率" value={s.success_rate ?? 0} unit="%" />
        <Kpi label="平均耗时" value={fmtDuration(s.avg_duration_sec ?? 0)} />
        <Kpi label="Token 消耗" value={fmtToken(s.total_tokens ?? 0)} />
        <Kpi label="LLM 调用次数" value={s.llm_calls ?? 0} unit="次" />
      </div>

      <div className="sec-title" style={{ display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
        调研项目
        <div style={{ flex: 1 }} />
        <button className="btn" onClick={() => setShowArchived(!showArchived)} style={{ fontSize: 12 }}>
          {showArchived ? '返回活动项目' : '查看归档'}
        </button>
      </div>

      {projects.length === 0 ? (
        <div className="empty">{showArchived ? '没有归档项目。' : '还没有项目，点左侧「新建调研」开始第一个课题。'}</div>
      ) : (
        <div className="proj-list">
          {projects.map((p) => (
            <div className="proj-row" key={p.id}>
              <div className="proj-main">
                <div className="proj-topic">
                  {p.topic || p.id}
                  {p.archived ? <span className="badge" style={{ marginLeft: '0.5rem' }}>已归档</span> : null}
                </div>
                <div className="proj-meta">
                  {p.relative_time || '—'} · 耗时 {fmtDuration(p.duration || 0)} · {p.n_charts} 图 · {p.n_tables} 表
                </div>
                {p.error && (
                  <div className="proj-meta" style={{ color: 'var(--danger)' }}>
                    ⚠ {p.error}
                  </div>
                )}
              </div>
              <StatusBadge status={p.status} />
              {p.error && (
                <button className="btn primary" onClick={() => retry(p)}>重试</button>
              )}
              {p.has_result || p.has_docx ? (
                <button className="btn" onClick={() => go(`/report/${p.id}`)}>查看报告</button>
              ) : (
                <button className="btn" onClick={() => go(`/report/${p.id}`)}>查看进度</button>
              )}
              <button className="btn" onClick={() => act(`/api/projects/${p.id}/duplicate`)}>复制</button>
              <button className="btn" onClick={() => rename(p)}>重命名</button>
              {p.archived ? (
                <button className="btn" onClick={() => act(`/api/projects/${p.id}/unarchive`)}>取消归档</button>
              ) : (
                <button className="btn" onClick={() => act(`/api/projects/${p.id}/archive`)}>归档</button>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
