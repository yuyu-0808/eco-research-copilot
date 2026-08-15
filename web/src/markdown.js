// 报告正文处理：占位符切分、标题提取、Markdown 渲染（对齐后端 src/ui/charts.py 逻辑）。
import { marked } from 'marked'

const PLACEHOLDER = /\[\[(CHART|TABLE):(\d+)\]\]/g

// 把报告 markdown 按 [[CHART:n]] / [[TABLE:n]] 切分成 (kind, text, index) 序列
export function splitReport(md) {
  if (!md) return [{ kind: 'text', text: '', index: null }]
  const parts = []
  let pos = 0
  let m
  PLACEHOLDER.lastIndex = 0
  while ((m = PLACEHOLDER.exec(md)) !== null) {
    if (m.index > pos) parts.push({ kind: 'text', text: md.slice(pos, m.index), index: null })
    parts.push({ kind: m[1], text: '', index: parseInt(m[2], 10) })
    pos = m.index + m[0].length
  }
  if (pos < md.length) parts.push({ kind: 'text', text: md.slice(pos), index: null })
  return parts
}

// 提取二级标题列表（报告目录导航）
export function extractHeadings(md) {
  if (!md) return []
  return (md.match(/^##\s+(.+)$/gm) || []).map((l) => l.replace(/^##\s+/, '').trim())
}

// Markdown 渲染为 HTML（用于报告正文）
export function renderMarkdown(md) {
  if (!md) return ''
  return marked.parse(md)
}

// 表格 dict → HTML（对齐后端 table_to_html）
function escapeHtml(s) {
  return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
}
export function tableToHtml(table) {
  if (!table || typeof table !== 'object') return ''
  const headers = table.headers || []
  const rows = table.rows || []
  if (!headers.length && !rows.length) return ''
  const head = headers.length
    ? '<thead><tr>' + headers.map((h) => `<th>${escapeHtml(h)}</th>`).join('') + '</tr></thead>'
    : ''
  const body =
    '<tbody>' +
    rows.map((r) => '<tr>' + r.map((c) => `<td>${escapeHtml(c)}</td>`).join('') + '</tr>').join('') +
    '</tbody>'
  return `<table class="report-table">${head}${body}</table>`
}
