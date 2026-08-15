import { useEffect, useRef, useState } from 'react'
import { apiGet, apiPut, apiPost } from '../api.js'

export default function Settings() {
  const [cfg, setCfg] = useState(null)
  const [err, setErr] = useState('')
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const fileRef = useRef(null)

  useEffect(() => {
    load()
  }, [])

  function load() {
    apiGet('/api/settings').then((c) => { setCfg(c); setSaved(false) }).catch((e) => setErr(e.message))
  }

  function set(key, value) {
    setCfg((c) => ({ ...c, [key]: value }))
    setSaved(false)
  }

  async function save() {
    setSaving(true)
    setErr('')
    try {
      await apiPut('/api/settings', cfg)
      setSaved(true)
    } catch (e) {
      setErr(e.message)
    } finally {
      setSaving(false)
    }
  }

  // 导出配置（不含密钥明文）
  function exportCfg() {
    const exportable = { ...cfg }
    delete exportable.deepseek_api_key_set
    delete exportable.deepseek_api_key_masked
    delete exportable.tavily_api_key_set
    delete exportable.tavily_api_key_masked
    delete exportable.deepseek_api_key
    delete exportable.tavily_api_key
    const blob = new Blob([JSON.stringify(exportable, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = 'eco-research-settings.json'
    a.click()
    URL.revokeObjectURL(url)
  }

  // 导入配置（覆盖非密钥字段）
  function importCfg(e) {
    const file = e.target.files?.[0]
    if (!file) return
    const reader = new FileReader()
    reader.onload = async () => {
      try {
        const obj = JSON.parse(reader.result)
        const payload = {}
        for (const k of Object.keys(obj)) {
          if (!['deepseek_api_key', 'tavily_api_key', 'deepseek_api_key_set', 'deepseek_api_key_masked', 'tavily_api_key_set', 'tavily_api_key_masked'].includes(k)) {
            payload[k] = obj[k]
          }
        }
        await apiPut('/api/settings', payload)
        load()
      } catch (err2) {
        setErr('导入失败：' + err2.message)
      }
    }
    reader.readAsText(file)
    e.target.value = ''
  }

  async function resetCfg() {
    if (!window.confirm('确认重置所有配置到默认值？（不影响已保存的 API 密钥）')) return
    try {
      await apiPost('/api/settings/reset')
      load()
    } catch (e) {
      setErr(e.message)
    }
  }

  if (err) return <div className="card">加载失败：{err}</div>
  if (!cfg) return <div className="empty"><span className="spin" /> 加载中…</div>

  return (
    <div style={{ maxWidth: 760 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '0.8rem', marginBottom: '0.6rem' }}>
        <div className="sec-title" style={{ margin: 0 }}>设置 · 系统参数</div>
        <div style={{ flex: 1 }} />
        <button className="btn" onClick={exportCfg}>导出配置</button>
        <button className="btn" onClick={() => fileRef.current?.click()}>导入配置</button>
        <input ref={fileRef} type="file" accept=".json" style={{ display: 'none' }} onChange={importCfg} />
        <button className="btn danger-ghost" onClick={resetCfg}>重置默认</button>
      </div>
      <div className="muted" style={{ fontSize: 13, marginBottom: '1rem' }}>
        修改后点「保存配置」生效，无需改 .env 文件。API 密钥只显示脱敏值，点击「编辑」可更换。
      </div>

      <Group title="模型配置" defaultOpen>
        <Field label="主模型"><input value={cfg.model_name} onChange={(e) => set('model_name', e.target.value)} /></Field>
        <Field label="备用模型（留空不启用）"><input value={cfg.backup_model} onChange={(e) => set('backup_model', e.target.value)} /></Field>
        <Field label="Base URL"><input value={cfg.base_url} onChange={(e) => set('base_url', e.target.value)} /></Field>
        <SecretField label="DeepSeek API Key" masked={cfg.deepseek_api_key_masked} onChange={(v) => set('deepseek_api_key', v)} />
      </Group>

      <Group title="搜索配置">
        <Field label="搜索引擎">
          <select value={cfg.search_provider} onChange={(e) => set('search_provider', e.target.value)}>
            <option value="tavily">Tavily（推荐，需密钥）</option>
            <option value="ddg">DuckDuckGo（可选代理）</option>
          </select>
        </Field>
        <SecretField label="Tavily API Key" masked={cfg.tavily_api_key_masked} onChange={(v) => set('tavily_api_key', v)} />
        <Field label="检索轮数上限">
          <input type="number" min="1" max="10" value={cfg.max_collect_rounds} onChange={(e) => set('max_collect_rounds', parseInt(e.target.value || '1', 10))} />
        </Field>
      </Group>

      <Group title="证据门槛">
        <Field label="严格熔断（证据不足强制终止）">
          <label style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', fontWeight: 400 }}>
            <input type="checkbox" checked={!!cfg.require_strict_evidence} onChange={(e) => set('require_strict_evidence', e.target.checked)} />
            开启质量门禁
          </label>
        </Field>
        <Field label="撰写-逻辑稽核交叉校验轮数">
          <input type="number" min="1" max="5" value={cfg.write_audit_rounds} onChange={(e) => set('write_audit_rounds', parseInt(e.target.value || '1', 10))} />
        </Field>
        <Field label="阶段失败自动重试次数">
          <input type="number" min="0" max="5" value={cfg.stage_retry} onChange={(e) => set('stage_retry', parseInt(e.target.value || '0', 10))} />
        </Field>
      </Group>

      <Group title="报告配置">
        <Field label="报告正文模式">
          <select value={cfg.report_mode} onChange={(e) => set('report_mode', e.target.value)}>
            <option value="standard">标准模式（快，一次性生成）</option>
            <option value="deep">深度模式（分章生成，更充实）</option>
          </select>
        </Field>
        <Field label="人机协同模式">
          <select value={cfg.review_mode} onChange={(e) => set('review_mode', e.target.value)}>
            <option value="auto">全自动（默认）</option>
            <option value="manual">三阶段确认（框架→素材→终稿）</option>
          </select>
        </Field>
      </Group>

      <Group title="报告模板（Word / PDF 通用）">
        <Field label="免责声明（留空用内置默认）">
          <textarea rows={2} value={cfg.report_disclaimer} onChange={(e) => set('report_disclaimer', e.target.value)} placeholder="自定义报告封面免责声明文案" />
        </Field>
        <Field label="页眉文本（留空用报告标题）">
          <input value={cfg.report_header} onChange={(e) => set('report_header', e.target.value)} placeholder="如：内部研究 · 仅供交流" />
        </Field>
        <Field label="页脚文本（留空用自动页码）">
          <input value={cfg.report_footer} onChange={(e) => set('report_footer', e.target.value)} placeholder="如：© 2026 Eco-Research" />
        </Field>
        <Field label="Logo 图片路径（留空不显示）">
          <input value={cfg.report_logo} onChange={(e) => set('report_logo', e.target.value)} placeholder="如：C:/path/to/logo.png" />
        </Field>
      </Group>

      <div style={{ marginTop: '1rem', display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
        <button className="btn primary" onClick={save} disabled={saving}>
          {saving ? (<><span className="spin" /> 保存中…</>) : '保存配置'}
        </button>
        {saved && <span className="badge ok">已保存并生效</span>}
      </div>
    </div>
  )
}

function Group({ title, children, defaultOpen = false }) {
  return (
    <details className="settings-group" open={defaultOpen}>
      <summary className="settings-summary">{title}</summary>
      <div className="settings-body">{children}</div>
    </details>
  )
}

function Field({ label, children }) {
  return (
    <div className="field">
      <label>{label}</label>
      {children}
    </div>
  )
}

function SecretField({ label, masked, onChange }) {
  const [editing, setEditing] = useState(false)
  return (
    <div className="field">
      <label>{label}</label>
      {editing ? (
        <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
          <input type="password" placeholder="输入新密钥" onChange={(e) => onChange(e.target.value)} style={{ flex: 1 }} />
          <button className="btn" style={{ flexShrink: 0 }} onClick={() => { setEditing(false); onChange('') }}>取消</button>
        </div>
      ) : (
        <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
          <code style={{ flex: 1, background: 'var(--surface-2)', padding: '0.55rem 0.8rem', borderRadius: 'var(--radius-sm)', fontSize: 13, color: masked ? 'var(--text)' : 'var(--muted)', border: '1px solid var(--border)' }}>
            {masked || '（未配置）'}
          </code>
          <button className="btn" style={{ flexShrink: 0 }} onClick={() => setEditing(true)}>编辑</button>
        </div>
      )}
    </div>
  )
}
