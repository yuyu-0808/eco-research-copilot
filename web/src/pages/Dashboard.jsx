import { useEffect, useState } from 'react'
import { apiGet, apiPost, apiDelete } from '../api.js'
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

function fmtDateTime(iso) {
  if (!iso) return ''
  try {
    const d = new Date(iso)
    if (isNaN(d.getTime())) return iso
    const p = (x) => String(x).padStart(2, '0')
    return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`
  } catch {
    return iso
  }
}

export default function Dashboard({ go }) {
  const [data, setData] = useState(null)
  const [stats, setStats] = useState(null)
  const [err, setErr] = useState('')
  const [toast, setToast] = useState('')
  const [showArchived, setShowArchived] = useState(false)
  const [selected, setSelected] = useState(new Set())

  function notify(msg) {
    setToast(msg)
    window.clearTimeout(notify._t)
    notify._t = window.setTimeout(() => setToast(''), 2400)
  }

  function load() {
    apiGet(`/api/projects${showArchived ? '?include_archived=1' : ''}`)
      .then(setData)
      .catch((e) => setErr(e.message))
  }
  useEffect(() => {
    load()
    apiGet('/api/stats').then(setStats).catch(() => {})
  }, [showArchived])

  async function act(path, body, successMsg) {
    try {
      await apiPost(path, body)
      load()
      if (successMsg) notify(successMsg)
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

  async function resume(p) {
    await act(`/api/projects/${p.id}/resume`)
    go(`/report/${p.id}`)
  }

  async function retry(p) {
    await act(`/api/projects/${p.id}/retry`)
    go(`/report/${p.id}`)
  }

  async function remove(p) {
    if (!window.confirm(`确认删除「${p.topic || p.id}」？此操作不可恢复。`)) return
    try {
      await apiDelete(`/api/projects/${p.id}`)
      load()
      notify('项目已删除')
    } catch (e) {
      setErr(e.message)
    }
  }

  if (err) return <div className="card">加载失败：{err}</div>
  if (!data) return <div className="empty"><span className="spin" /> 加载中…</div>

  const { projects } = data
  const m = data.metrics || {}
  const s = stats || {}

  // 全选 / 反选 / 批量删除
  const allChecked = projects.length > 0 && projects.every((p) => selected.has(p.id))
  function toggleAll() {
    setSelected(allChecked ? new Set() : new Set(projects.map((p) => p.id)))
  }
  function toggleOne(id) {
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }
  async function removeSelected() {
    if (selected.size === 0) return
    if (!window.confirm(`确认删除选中的 ${selected.size} 个项目？此操作不可恢复。`)) return
    try {
      await apiPost('/api/projects/batch_delete', { ids: [...selected] })
      setSelected(new Set())
      load()
      notify(`已删除 ${selected.size} 个项目`)
    } catch (e) { setErr(e.message) }
  }

  return (
    <div>
      {toast && <div className="toast">✓ {toast}</div>}
      <div className="sec-title">工作台 · 概览</div>
      <div className="kpi-groups">
        <KpiGroup title="产出" items={[
          { label: '累计调研', value: m.total ?? projects.length, unit: '个' },
          { label: '生成图表', value: m.charts ?? 0, unit: '张' },
        ]} />
        <KpiGroup title="质量" items={[
          { label: '质检通过率', value: m.qa_rate ?? 0, unit: '%' },
          { label: '任务成功率', value: s.success_rate ?? 0, unit: '%' },
        ]} />
        <KpiGroup title="效率" items={[
          { label: '平均耗时', value: fmtDuration(s.avg_duration_sec ?? 0) },
          { label: 'Token 消耗', value: fmtToken(s.total_tokens ?? 0) },
        ]} />
      </div>

      <div className="sec-title" style={{ display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
        调研项目
        {projects.length > 0 && (
          <label style={{ display: 'inline-flex', alignItems: 'center', gap: '0.3rem', fontSize: 12, fontWeight: 400, color: 'var(--muted)' }}>
            <input type="checkbox" checked={allChecked} onChange={toggleAll} /> 全选
          </label>
        )}
        <div style={{ flex: 1 }} />
        {selected.size > 0 && (
          <button className="btn" style={{ fontSize: 12, color: 'var(--danger)', borderColor: 'var(--danger)' }} onClick={removeSelected}>
            删除选中 ({selected.size})
          </button>
        )}
        <button className="btn" onClick={() => setShowArchived(!showArchived)} style={{ fontSize: 12 }}>
          {showArchived ? '返回活动项目' : '查看归档'}
        </button>
      </div>

      {projects.length === 0 ? (
        <div className="card empty-hero">
          <div className="empty-emoji">{showArchived ? '🗂️' : '🚀'}</div>
          <div className="empty-title">{showArchived ? '没有归档项目' : '开始你的第一份深度报告'}</div>
          <div className="empty-desc">
            {showArchived ? '归档的项目会显示在这里。' : '输入一个课题，多智能体会自动完成检索、验证、分析与报告撰写。'}
          </div>
          {!showArchived && (
            <button className="btn primary" onClick={() => go('/new')}>＋ 新建调研</button>
          )}
        </div>
      ) : (
        <div className="proj-list">
          {projects.map((p) => (
            <div className="proj-row" key={p.id}>
              <div style={{ display: 'flex', alignItems: 'center', paddingRight: '0.6rem' }}>
                <input type="checkbox" checked={selected.has(p.id)} onChange={() => toggleOne(p.id)} />
              </div>
              <div className="proj-main">
                <div className="proj-topic">
                  {p.topic || p.id}
                  {p.archived ? <span className="badge" style={{ marginLeft: '0.5rem' }}>已归档</span> : null}
                </div>
                <div className="proj-meta">
                  创建 {p.relative_time || '—'} · 耗时 {fmtDuration(p.duration || 0)}
                  {p.n_charts || p.n_tables ? ` · ${p.n_charts} 图 · ${p.n_tables} 表` : ''}
                  {p.completed_at ? ` · 完成 ${fmtDateTime(p.completed_at)}` : ''}
                </div>
                {p.error && (
                  <div className="proj-meta" style={{ color: 'var(--danger)' }}>⚠ {p.error}</div>
                )}
              </div>
              <StatusBadge status={p.status} />
              <div className="proj-actions">
                {p.status === 'completed' ? (
                  <button className="btn" onClick={() => go(`/report/${p.id}`)}>查看报告</button>
                ) : p.status === 'running' ? (
                  <button className="btn" onClick={() => go(`/report/${p.id}`)}>查看进度</button>
                ) : p.status === 'paused' ? (
                  <button className="btn primary" onClick={() => resume(p)}>继续</button>
                ) : p.status === 'failed' || p.status === 'stopped' ? (
                  <button className="btn primary" onClick={() => retry(p)}>重试</button>
                ) : p.resumable ? (
                  <button className="btn primary" onClick={() => resume(p)}>继续</button>
                ) : (
                  <button className="btn" onClick={() => go(`/report/${p.id}`)}>查看</button>
                )}
                <button className="btn danger-ghost" onClick={() => remove(p)}>删除</button>
                <details className="more-menu">
                  <summary className="btn">⋯</summary>
                  <div className="more-items">
                    <button onClick={() => act(`/api/projects/${p.id}/duplicate`)}>复制</button>
                    <button onClick={() => rename(p)}>重命名</button>
                    {p.archived
                      ? <button onClick={() => act(`/api/projects/${p.id}/unarchive`)}>取消归档</button>
                      : <button onClick={() => act(`/api/projects/${p.id}/archive`)}>归档</button>}
                  </div>
                </details>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

function KpiGroup({ title, items }) {
  return (
    <div className="kpi-group">
      <div className="kpi-group-title">{title}</div>
      {items.map((it, i) => (
        <Kpi key={i} label={it.label} value={it.value} unit={it.unit} />
      ))}
    </div>
  )
}
