import { useEffect, useState } from 'react'
import {
  DndContext, closestCenter, PointerSensor, useSensor, useSensors,
} from '@dnd-kit/core'
import {
  SortableContext, verticalListSortingStrategy, useSortable, arrayMove,
} from '@dnd-kit/sortable'
import { CSS } from '@dnd-kit/utilities'
import { apiGet, apiPost, apiPut } from '../api.js'
import { TierBadge } from '../components.jsx'

const STAGE_LABEL = { framework: '框架确认', materials: '素材确认', draft: '终稿确认' }
const TIERS = ['A', 'B', 'C', 'D', 'E', 'F']
let _uid = 0
const uid = () => `sec_${++_uid}`

export default function ReviewPanel({ projectId, reviewStage, onDone }) {
  const [data, setData] = useState(null)
  const [err, setErr] = useState('')
  const [saving, setSaving] = useState(false)

  async function load() {
    try {
      setData(await apiGet(`/api/projects/${projectId}/review`))
    } catch (e) {
      setErr(e.message)
    }
  }
  useEffect(() => { load() }, [projectId])

  async function confirm() {
    setSaving(true)
    try {
      await apiPost(`/api/projects/${projectId}/review/confirm`)
      onDone()
    } catch (e) {
      setErr(e.message)
      setSaving(false)
    }
  }

  if (err) return <div className="card">加载失败：{err}</div>
  if (!data) return <div className="empty"><span className="spin" /> 加载确认点…</div>

  return (
    <div className="card" style={{ borderColor: 'var(--brand)' }}>
      <div className="sec-title" style={{ margin: '0 0 0.8rem' }}>
        🧭 人工确认点 · {STAGE_LABEL[reviewStage] || reviewStage}
      </div>
      {reviewStage === 'framework' && <FrameworkEdit data={data} onSaved={load} />}
      {reviewStage === 'materials' && <MaterialsEdit data={data} onSaved={load} />}
      {reviewStage === 'draft' && <DraftEdit data={data} onSaved={load} />}
      <div style={{ marginTop: '1.1rem', display: 'flex', gap: '0.6rem' }}>
        <button className="btn primary" onClick={confirm} disabled={saving}>
          {saving ? (<><span className="spin" /> 确认中…</>) : '确认通过，继续执行'}
        </button>
      </div>
    </div>
  )
}

/* ---------------- 框架确认：拖拽排序 + 增删 + 门槛编辑 ---------------- */

function FrameworkEdit({ data, onSaved }) {
  const [sections, setSections] = useState(
    (data.sections || []).map((s) => ({ ...s, key: uid() })),
  )
  const [saved, setSaved] = useState(false)
  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 6 } }))

  function onDragEnd(e) {
    const { active, over } = e
    if (over && active.id !== over.id) {
      setSections((items) => {
        const oldIndex = items.findIndex((i) => i.key === active.id)
        const newIndex = items.findIndex((i) => i.key === over.id)
        return arrayMove(items, oldIndex, newIndex)
      })
      setSaved(false)
    }
  }

  function patch(key, field, value) {
    setSections((items) => items.map((i) => (i.key === key ? { ...i, [field]: value } : i)))
    setSaved(false)
  }
  function remove(key) {
    setSections((items) => items.filter((i) => i.key !== key))
    setSaved(false)
  }
  function add() {
    setSections((items) => [
      ...items,
      { key: uid(), title: '', question: '', metrics: [], min_evidence: 2, min_tier: 'C' },
    ])
    setSaved(false)
  }

  async function save() {
    await apiPut(`/api/projects/${data.project_id}/review/framework`, { sections })
    setSaved(true)
    onSaved && onSaved()
  }

  return (
    <div>
      <div className="muted" style={{ fontSize: 13, marginBottom: '0.7rem' }}>
        拖拽章节调整顺序，可增删章节、修改每章的证据数量与信源等级门槛，保存后实时生效。
      </div>
      <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={onDragEnd}>
        <SortableContext items={sections.map((s) => s.key)} strategy={verticalListSortingStrategy}>
          {sections.map((s, idx) => (
            <SortableSection
              key={s.key}
              section={s}
              index={idx}
              onPatch={(f, v) => patch(s.key, f, v)}
              onRemove={() => remove(s.key)}
            />
          ))}
        </SortableContext>
      </DndContext>
      <button className="btn" onClick={add} style={{ marginTop: '0.5rem' }}>＋ 新增章节</button>
      <div style={{ marginTop: '1rem' }}>
        <button className="btn" onClick={save}>保存框架编辑</button>
        {saved && <span className="badge ok" style={{ marginLeft: '0.6rem' }}>已保存</span>}
      </div>
    </div>
  )
}

function SortableSection({ section, index, onPatch, onRemove }) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({ id: section.key })
  const style = { transform: CSS.Transform.toString(transform), transition, opacity: isDragging ? 0.5 : 1 }
  return (
    <div ref={setNodeRef} style={style} className="card" >
      <div style={{ display: 'flex', gap: '0.6rem', alignItems: 'flex-start' }}>
        <button
          className="btn"
          style={{ cursor: 'grab', padding: '0.5rem 0.6rem', flexShrink: 0 }}
          {...attributes}
          {...listeners}
          title="拖拽排序"
        >≡</button>
        <div style={{ flex: 1 }}>
          <div style={{ display: 'flex', gap: '0.6rem', alignItems: 'center' }}>
            <b style={{ color: 'var(--brand-ink)' }}>{index + 1}.</b>
            <input
              style={{ flex: 1 }}
              value={section.title}
              placeholder="章节标题"
              onChange={(e) => onPatch('title', e.target.value)}
            />
            <button className="btn" onClick={onRemove} style={{ color: 'var(--danger)' }}>删除</button>
          </div>
          <div style={{ display: 'flex', gap: '0.6rem', marginTop: '0.5rem', flexWrap: 'wrap' }}>
            <input
              style={{ flex: 2, minWidth: 220 }}
              value={section.question}
              placeholder="该章必答问题"
              onChange={(e) => onPatch('question', e.target.value)}
            />
            <label style={{ fontSize: 12, display: 'flex', alignItems: 'center', gap: '0.3rem' }}>
              最少证据
              <input
                type="number" min="1" max="10" style={{ width: 56 }}
                value={section.min_evidence}
                onChange={(e) => onPatch('min_evidence', parseInt(e.target.value || '1', 10))}
              />
            </label>
            <label style={{ fontSize: 12, display: 'flex', alignItems: 'center', gap: '0.3rem' }}>
              最低信源
              <select value={section.min_tier} onChange={(e) => onPatch('min_tier', e.target.value)}>
                {TIERS.map((t) => <option key={t} value={t}>{t} 级</option>)}
              </select>
            </label>
          </div>
        </div>
      </div>
    </div>
  )
}

/* ---------------- 素材确认：信源卡片增删 / 评级 / 必采 ---------------- */

function MaterialsEdit({ data, onSaved }) {
  const [items, setItems] = useState((data.evidence || []).map((e) => ({ ...e, _key: uid() })))
  const [saved, setSaved] = useState(false)

  function patch(key, field, value) {
    setItems((list) => list.map((i) => (i._key === key ? { ...i, [field]: value } : i)))
    setSaved(false)
  }
  function remove(key) {
    setItems((list) => list.map((i) => (i._key === key ? { ...i, removed: true } : i)))
    setSaved(false)
  }
  function restore(key) {
    setItems((list) => list.map((i) => (i._key === key ? { ...i, removed: false } : i)))
    setSaved(false)
  }
  function add() {
    setItems((list) => [
      ...list,
      { _key: uid(), claim: '', value: '', period: '', source_tier: 'C', source_title: '', source_url: '', publisher: '', section: '', removed: false, must_use: false },
    ])
    setSaved(false)
  }

  async function save() {
    const cleaned = items.map(({ _key, ...rest }) => rest)
    await apiPut(`/api/projects/${data.project_id}/review/materials`, { evidence: cleaned })
    setSaved(true)
    onSaved && onSaved()
  }

  const kept = items.filter((i) => !i.removed).length

  return (
    <div>
      <div className="muted" style={{ fontSize: 13, marginBottom: '0.7rem' }}>
        信源以卡片展示，可剔除无效信源、调整信源评级、标记「必采」，或补充新信源。当前保留 {kept} / {items.length} 条。
      </div>
      {items.map((it) => (
        <div key={it._key} className={`ev-row ${it.removed ? '' : ''}`} style={it.removed ? { opacity: 0.45 } : {}}>
          <div className="ev-head" style={{ gap: '0.5rem' }}>
            <select value={it.source_tier} onChange={(e) => patch(it._key, 'source_tier', e.target.value)}>
              {TIERS.map((t) => <option key={t} value={t}>{t} · {TIER_LABEL[t]}</option>)}
            </select>
            <span className="ev-claim" style={{ flex: 1 }}>{it.claim || '（新信源）'}</span>
            {it.must_use && <span className="badge brand">必采</span>}
            {it.removed
              ? <button className="btn" onClick={() => restore(it._key)}>恢复</button>
              : <button className="btn" style={{ color: 'var(--danger)' }} onClick={() => remove(it._key)}>剔除</button>}
          </div>
          <div className="ev-meta">
            {it.publisher || '未知机构'}
            {it.value ? ` · ${it.value}${it.unit || ''}` : ''}
            {it.period ? ` · ${it.period}` : ''}
            {it.source_url ? <> · <a href={it.source_url} target="_blank" rel="noreferrer">{it.source_title || '来源'}</a></> : ''}
          </div>
          <div style={{ marginTop: '0.4rem', display: 'flex', gap: '0.6rem', alignItems: 'center' }}>
            <label style={{ fontSize: 12, display: 'flex', alignItems: 'center', gap: '0.3rem' }}>
              <input type="checkbox" checked={!!it.must_use} onChange={(e) => patch(it._key, 'must_use', e.target.checked)} />
              标记必采
            </label>
          </div>
        </div>
      ))}
      <button className="btn" onClick={add} style={{ marginTop: '0.5rem' }}>＋ 补充信源</button>
      <div style={{ marginTop: '1rem' }}>
        <button className="btn" onClick={save}>保存素材编辑</button>
        {saved && <span className="badge ok" style={{ marginLeft: '0.6rem' }}>已保存</span>}
      </div>
    </div>
  )
}

const TIER_LABEL = { A: '一手官方', B: '权威媒体', C: '行业专业', D: '一般来源', E: '低质来源', F: '无法判断' }

/* ---------------- 终稿确认：正文编辑 ---------------- */

function DraftEdit({ data, onSaved }) {
  const [markdown, setMarkdown] = useState(data.markdown || '')
  const [saved, setSaved] = useState(false)

  async function save() {
    await apiPut(`/api/projects/${data.project_id}/review/draft`, { markdown })
    setSaved(true)
    onSaved && onSaved()
  }

  const cov = data.coverage || {}
  return (
    <div>
      {Object.keys(cov).length > 0 && (
        <div className="muted" style={{ fontSize: 13, marginBottom: '0.6rem' }}>
          证据覆盖（question_id=条数）：{Object.entries(cov).map(([k, v]) => `${k}=${v}`).join(' · ')}
        </div>
      )}
      <textarea rows={18} value={markdown} onChange={(e) => setMarkdown(e.target.value)} style={{ width: '100%', fontFamily: 'monospace', fontSize: 13 }} />
      <div style={{ marginTop: '0.8rem' }}>
        <button className="btn" onClick={save}>保存终稿</button>
        {saved && <span className="badge ok" style={{ marginLeft: '0.6rem' }}>已保存</span>}
      </div>
    </div>
  )
}
