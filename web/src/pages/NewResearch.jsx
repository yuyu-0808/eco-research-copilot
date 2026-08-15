import { useState } from 'react'
import { apiPost } from '../api.js'

export default function NewResearch({ go }) {
  const [topic, setTopic] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')

  async function launch() {
    const t = topic.trim()
    if (!t) { setErr('请先输入调研课题。'); return }
    setBusy(true)
    setErr('')
    try {
      // 1. 创建项目
      const proj = await apiPost('/api/projects', { topic: t })
      // 2. 提交任务到后台队列（非阻塞）
      await apiPost(`/api/projects/${proj.project_id}/run`, { topic: t })
      go(`/report/${proj.project_id}`)
    } catch (e) {
      setErr(e.message)
      setBusy(false)
    }
  }

  return (
    <div style={{ maxWidth: 640 }}>
      <div className="sec-title">新建调研</div>
      <div className="card">
        <div className="field">
          <label>调研课题</label>
          <textarea
            rows={3}
            placeholder="输入你想调研的行业 / 市场 / 政策议题…"
            value={topic}
            onChange={(e) => setTopic(e.target.value)}
          />
        </div>
        <div className="muted" style={{ fontSize: 13, marginBottom: '1rem' }}>
          提交后由多智能体自动完成「框架匹配 → 信源检索 → 代码稽核 → 结构化提炼 → 撰写 → 渲染」全流程，可随时查看进度与溯源报告。
        </div>
        {err && <div className="badge danger" style={{ marginBottom: '0.8rem' }}>{err}</div>}
        <button className="btn primary" onClick={launch} disabled={busy}>
          {busy ? (<><span className="spin" /> 启动中…</>) : '启动智能体调研'}
        </button>
      </div>
    </div>
  )
}
