import { useEffect, useState } from 'react'
import { apiGet, apiPost, apiPut } from '../api.js'

// 示例课题（卡片式，点击填充输入框）
const EXAMPLES = [
  { icon: '🚗', tag: '新能源汽车', text: '2024年泰国新能源汽车渗透率、销量分析及政策影响' },
  { icon: '🔋', tag: '储能锂电', text: '2024年中国储能锂电池出货量、头部厂商份额及海外市场趋势' },
  { icon: '🧠', tag: 'AI 芯片', text: '全球AI芯片市场规模2024-2026预测及主要厂商竞争格局' },
  { icon: '🏭', tag: '碳关税', text: '欧盟CBAM碳关税对中国钢铁出口的影响及应对策略' },
]

// 调研模式（可视化三卡片）
const MODES = [
  { key: 'quick', icon: '⚡', name: '快速模式', desc: '一次性生成，最快出结果', report_mode: 'standard', review_mode: 'auto' },
  { key: 'deep', icon: '📊', name: '深度模式', desc: '分章生成，内容更充实', report_mode: 'deep', review_mode: 'auto' },
  { key: 'manual', icon: '👤', name: '人机协同', desc: '框架 / 素材 / 终稿三阶段确认', report_mode: 'standard', review_mode: 'manual' },
]

export default function NewResearch({ go }) {
  const [topic, setTopic] = useState('')
  const [frameworks, setFrameworks] = useState([])
  const [fwKey, setFwKey] = useState('') // '' = 自动匹配
  const [mode, setMode] = useState('deep')
  const [showAdvanced, setShowAdvanced] = useState(false)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')

  const [showUpload, setShowUpload] = useState(false)
  const [yamlText, setYamlText] = useState('')
  const [uploading, setUploading] = useState(false)

  // 高级设置（提交时覆盖全局默认）
  const [adv, setAdv] = useState({
    model_name: '', backup_model: '', search_provider: '',
    max_collect_rounds: '', require_strict_evidence: null,
  })

  useEffect(() => {
    apiGet('/api/frameworks')
      .then((d) => setFrameworks(d.frameworks || []))
      .catch(() => {})
    apiGet('/api/settings')
      .then((c) => setAdv((a) => ({
        ...a,
        model_name: c.model_name || '',
        backup_model: c.backup_model || '',
        search_provider: c.search_provider || '',
        max_collect_rounds: c.max_collect_rounds || '',
        require_strict_evidence: !!c.require_strict_evidence,
      })))
      .catch(() => {})
  }, [])

  const selected = frameworks.find((f) => f.key === fwKey) || null

  const setAdvField = (k) => (e) =>
    setAdv((a) => ({ ...a, [k]: e.target.type === 'checkbox' ? e.target.checked : e.target.value }))

  async function launch() {
    const t = topic.trim()
    if (!t) { setErr('请先输入或选择一个调研课题。'); return }
    setBusy(true)
    setErr('')
    try {
      // 1. 调研模式 + 高级设置写入全局配置（即时生效）
      const m = MODES.find((x) => x.key === mode) || MODES[1]
      const overrides = { report_mode: m.report_mode, review_mode: m.review_mode }
      if (adv.model_name) overrides.model_name = adv.model_name
      if (adv.backup_model) overrides.backup_model = adv.backup_model
      if (adv.search_provider) overrides.search_provider = adv.search_provider
      if (adv.max_collect_rounds) overrides.max_collect_rounds = parseInt(adv.max_collect_rounds, 10)
      if (adv.require_strict_evidence !== null) overrides.require_strict_evidence = adv.require_strict_evidence
      await apiPut('/api/settings', overrides)

      // 2. 创建项目并提交后台队列
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
      setFwKey(r.key)
      setYamlText('')
      setShowUpload(false)
    } catch (e) {
      setErr(e.message)
    } finally {
      setUploading(false)
    }
  }

  return (
    <div>
      <div className="sec-title">新建调研</div>

      {/* 示例课题卡片 */}
      <div className="sec-title" style={{ marginTop: '0.4rem' }}>示例课题</div>
      <div className="example-grid">
        {EXAMPLES.map((ex) => (
          <div
            key={ex.tag}
            className={`example-card ${topic === ex.text ? 'active' : ''}`}
            onClick={() => setTopic(ex.text)}
          >
            <div className="example-icon">{ex.icon}</div>
            <div className="example-tag">{ex.tag}</div>
            <div className="example-text">{ex.text}</div>
          </div>
        ))}
      </div>

      <div className="sec-title">调研课题</div>
      <div className="card">
        <div className="field">
          <textarea
            rows={3}
            placeholder="输入你想调研的行业 / 市场 / 政策议题，或点上方示例课题…"
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
      </div>

      {/* 调研模式 */}
      <div className="sec-title">调研模式</div>
      <div className="mode-grid">
        {MODES.map((m) => (
          <div
            key={m.key}
            className={`mode-card ${mode === m.key ? 'active' : ''}`}
            onClick={() => setMode(m.key)}
          >
            <div className="mode-icon">{m.icon}</div>
            <div className="mode-name">{m.name}</div>
            <div className="mode-desc">{m.desc}</div>
          </div>
        ))}
      </div>

      {/* 高级设置 */}
      <div className="sec-title">
        高级设置
        <button className="btn" style={{ marginLeft: 'auto', padding: '0.2rem 0.7rem', fontSize: 12 }} onClick={() => setShowAdvanced(!showAdvanced)}>
          {showAdvanced ? '收起' : '展开'}
        </button>
      </div>
      {showAdvanced && (
        <div className="adv-groups">
          <div className="card">
            <div className="adv-group-title">模型</div>
            <div className="field">
              <label>主模型</label>
              <input value={adv.model_name} onChange={setAdvField('model_name')} placeholder="如 deepseek-v4-flash" />
            </div>
            <div className="field">
              <label>备用模型（留空不启用）</label>
              <input value={adv.backup_model} onChange={setAdvField('backup_model')} placeholder="可选" />
            </div>
          </div>
          <div className="card">
            <div className="adv-group-title">搜索</div>
            <div className="field">
              <label>搜索引擎</label>
              <select value={adv.search_provider} onChange={setAdvField('search_provider')}>
                <option value="">（沿用全局）</option>
                <option value="tavily">Tavily（推荐）</option>
                <option value="ddg">DuckDuckGo</option>
              </select>
            </div>
            <div className="field">
              <label>检索轮数上限</label>
              <input type="number" min="1" max="10" value={adv.max_collect_rounds} onChange={setAdvField('max_collect_rounds')} />
            </div>
          </div>
          <div className="card">
            <div className="adv-group-title">证据</div>
            <div className="field">
              <label style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', fontWeight: 400 }}>
                <input type="checkbox" checked={!!adv.require_strict_evidence} onChange={setAdvField('require_strict_evidence')} />
                严格熔断（证据不足强制终止）
              </label>
            </div>
          </div>
        </div>
      )}

      <div style={{ marginTop: '0.4rem' }}>
        <button className="btn" onClick={() => setShowUpload(!showUpload)}>
          {showUpload ? '收起上传' : '＋ 上传自定义 YAML 框架'}
        </button>
      </div>
      {showUpload && (
        <div className="field" style={{ marginTop: '0.6rem' }}>
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
      <button className="btn primary" onClick={launch} disabled={busy} style={{ padding: '0.7rem 1.4rem' }}>
        {busy ? (<><span className="spin" /> 启动中…</>) : '启动智能体调研'}
      </button>
    </div>
  )
}

function FrameworkPreview({ fw }) {
  const sections = fw.sections || []
  return (
    <div className="card" style={{ background: 'var(--surface-2)', marginTop: '0.8rem' }}>
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
