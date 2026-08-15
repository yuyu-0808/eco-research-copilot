import { useEffect, useState } from 'react'
import { apiGet, apiPost } from '../api.js'

export default function NewResearch({ go }) {
  const [topic, setTopic] = useState('')
  const [frameworks, setFrameworks] = useState([])
  const [fwKey, setFwKey] = useState('') // '' = 自动匹配
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')

  const [showUpload, setShowUpload] = useState(false)
  const [yamlText, setYamlText] = useState('')
  const [uploading, setUploading] = useState(false)

  useEffect(() => {
    apiGet('/api/frameworks')
      .then((d) => setFrameworks(d.frameworks || []))
      .catch(() => {})
  }, [])

  const selected = frameworks.find((f) => f.key === fwKey) || null

  async function launch() {
    const t = topic.trim()
    if (!t) { setErr('请先输入调研课题。'); return }
    setBusy(true)
    setErr('')
    try {
      const proj = await apiPost('/api/projects', { topic: t, framework_key: fwKey })
      await apiPost(`/api/projects/${proj.project_id}/run`, { topic: t })
      go(`/report/${proj.project_id}`)
    } catch (e) {
      setErr(e.message)
      setBusy(false)
    }
  }

  async function uploadYaml() {
    const t = yamlText.trim()
    if (!t) { setErr('请粘贴自定义框架 YAML 内容。'); return }
    setUploading(true)
    setErr('')
    try {
      const r = await apiPost('/api/frameworks/upload', { yaml: t })
      const d = await apiGet('/api/frameworks')
      setFrameworks(d.frameworks || [])
      setFwKey(r.key) // 自动选中刚上传的框架
      setYamlText('')
      setShowUpload(false)
    } catch (e) {
      setErr(e.message)
    } finally {
      setUploading(false)
    }
  }

  return (
    <div style={{ maxWidth: 720 }}>
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

        <div className="field">
          <label>行业框架</label>
          <select value={fwKey} onChange={(e) => setFwKey(e.target.value)}>
            <option value="">自动匹配（按课题关键词）</option>
            {frameworks.map((f) => (
              <option key={f.key} value={f.key}>
                {f.name}{f._source?.includes('custom') ? '（自定义）' : ''}
              </option>
            ))}
          </select>
        </div>

        {selected && <FrameworkPreview fw={selected} />}

        <div style={{ marginBottom: '0.8rem' }}>
          <button className="btn" onClick={() => setShowUpload(!showUpload)}>
            {showUpload ? '收起上传' : '＋ 上传自定义 YAML 框架'}
          </button>
        </div>
        {showUpload && (
          <div className="field">
            <label>自定义框架 YAML（key / name / sections 结构，参考 frameworks/ 目录）</label>
            <textarea
              rows={10}
              placeholder={'key: my_industry\nname: 我的行业\nsections:\n  - title: 一、行业概览\n    question: ...\n    metrics: [...]\n    min_evidence: 2\n    min_tier: B'}
              style={{ fontFamily: 'monospace', fontSize: 12 }}
              value={yamlText}
              onChange={(e) => setYamlText(e.target.value)}
            />
            <button className="btn" onClick={uploadYaml} disabled={uploading} style={{ marginTop: '0.5rem' }}>
              {uploading ? (<><span className="spin" /> 上传中…</>) : '上传并启用'}
            </button>
          </div>
        )}

        <div className="muted" style={{ fontSize: 13, margin: '0.8rem 0 1rem' }}>
          提交后由多智能体自动完成「框架匹配 → 信源检索 → 代码稽核 → 结构化提炼 → 撰写 → 渲染」全流程。
        </div>
        {err && <div className="badge danger" style={{ marginBottom: '0.8rem' }}>{err}</div>}
        <button className="btn primary" onClick={launch} disabled={busy}>
          {busy ? (<><span className="spin" /> 启动中…</>) : '启动智能体调研'}
        </button>
      </div>
    </div>
  )
}

function FrameworkPreview({ fw }) {
  const sections = fw.sections || []
  return (
    <div className="card" style={{ background: 'var(--surface-2)', marginBottom: '0.8rem' }}>
      <div style={{ fontWeight: 700, fontSize: 14, marginBottom: '0.4rem' }}>框架预览：{fw.name}</div>
      <div className="muted" style={{ fontSize: 12, marginBottom: '0.6rem' }}>
        核心指标 {Object.keys(fw.metrics_library || {}).length} 项 · 重点公司 {(fw.key_players || []).length} 家
      </div>
      {sections.map((s, i) => (
        <div key={i} style={{ fontSize: 13, padding: '0.25rem 0' }}>
          <b style={{ color: 'var(--brand-ink)' }}>{i + 1}. {s.title}</b>
          <span className="muted"> · {s.question}</span>
          <span className="muted" style={{ fontSize: 11 }}>（证据 ≥{s.min_evidence} · 信源 ≥{s.min_tier}级）</span>
        </div>
      ))}
      {(fw.key_players || []).length > 0 && (
        <div className="muted" style={{ fontSize: 12, marginTop: '0.4rem' }}>
          重点公司：{(fw.key_players || []).slice(0, 6).join('、')}{fw.key_players.length > 6 ? ' 等' : ''}
        </div>
      )}
    </div>
  )
}
