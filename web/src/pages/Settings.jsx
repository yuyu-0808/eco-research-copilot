import { useEffect, useState } from 'react'
import { apiGet, apiPut } from '../api.js'

export default function Settings() {
  const [cfg, setCfg] = useState(null)
  const [err, setErr] = useState('')
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)

  useEffect(() => {
    apiGet('/api/settings').then(setCfg).catch((e) => setErr(e.message))
  }, [])

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

  if (err) return <div className="card">加载失败：{err}</div>
  if (!cfg) return <div className="empty"><span className="spin" /> 加载中…</div>

  return (
    <div style={{ maxWidth: 720 }}>
      <div className="sec-title">设置 · 系统参数</div>
      <div className="muted" style={{ fontSize: 13, marginBottom: '1rem' }}>
        修改立即生效，无需改 .env 文件。API 密钥只显示是否已配置，留空则不修改。
      </div>

      <Group title="模型配置">
        <Field label="主模型"><input value={cfg.model_name} onChange={(e) => set('model_name', e.target.value)} /></Field>
        <Field label="备用模型（留空不启用）"><input value={cfg.backup_model} onChange={(e) => set('backup_model', e.target.value)} /></Field>
        <Field label="Base URL"><input value={cfg.base_url} onChange={(e) => set('base_url', e.target.value)} /></Field>
        <Field label={`DeepSeek API Key ${cfg.deepseek_api_key_set ? '（已配置）' : '（未配置）'}`}>
          <input type="password" placeholder={cfg.deepseek_api_key_set ? '已配置，留空则不修改' : '请输入'} onChange={(e) => set('deepseek_api_key', e.target.value)} />
        </Field>
      </Group>

      <Group title="搜索配置">
        <Field label="搜索引擎">
          <select value={cfg.search_provider} onChange={(e) => set('search_provider', e.target.value)}>
            <option value="tavily">Tavily（推荐，需密钥）</option>
            <option value="ddg">DuckDuckGo（可选代理）</option>
          </select>
        </Field>
        <Field label={`Tavily API Key ${cfg.tavily_api_key_set ? '（已配置）' : '（未配置）'}`}>
          <input type="password" placeholder={cfg.tavily_api_key_set ? '已配置，留空则不修改' : '请输入'} onChange={(e) => set('tavily_api_key', e.target.value)} />
        </Field>
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

      <div style={{ marginTop: '1rem', display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
        <button className="btn primary" onClick={save} disabled={saving}>
          {saving ? (<><span className="spin" /> 保存中…</>) : '保存配置'}
        </button>
        {saved && <span className="badge ok">已保存并生效</span>}
      </div>
    </div>
  )
}

function Group({ title, children }) {
  return (
    <div className="card" style={{ marginBottom: '1rem' }}>
      <div className="sec-title" style={{ margin: '0 0 0.6rem' }}>{title}</div>
      {children}
    </div>
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
