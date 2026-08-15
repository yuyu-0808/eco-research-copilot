import { useEffect, useRef } from 'react'
import * as echarts from 'echarts'

const TIER_LABEL = {
  A: '一手官方', B: '权威媒体', C: '行业专业', D: '一般来源', E: '低质来源', F: '无法判断',
}
const STAGE_NAMES = ['架构', '检索', '稽核', '提炼', '撰写', '渲染']

// 信源等级徽章 A-F
export function TierBadge({ tier }) {
  const t = tier || 'D'
  return <span className={`badge badge-grade-${t.toLowerCase()}`}>{t} · {TIER_LABEL[t] || '未知'}</span>
}

// 状态徽章
export function StatusBadge({ status }) {
  if (status === 'completed') return <span className="badge ok">已完成</span>
  if (status === 'running') return <span className="badge brand">运行中</span>
  if (status === 'paused') return <span className="badge part">已暂停</span>
  if (status === 'failed') return <span className="badge danger">失败</span>
  if (status === 'stopped') return <span className="badge danger">已终止</span>
  return <span className="badge part">进行中 / 中断</span>
}

// 6 步流水线可视化
export function Pipeline({ stages }) {
  const list = stages && stages.length ? stages : ['pending', 'pending', 'pending', 'pending', 'pending', 'pending']
  return (
    <div className="pipeline">
      {STAGE_NAMES.map((name, i) => (
        <div key={i} className={`stage ${list[i] || 'pending'}`}>
          <div className="dot">{i + 1}</div>
          <div className="name">{name}</div>
        </div>
      ))}
    </div>
  )
}

// KPI 卡片
export function Kpi({ label, value, unit }) {
  return (
    <div className="kpi">
      <div className="kpi-label">{label}</div>
      <div className="kpi-value">
        {value}
        {unit ? <span className="unit">{unit}</span> : null}
      </div>
    </div>
  )
}

// 日志面板
export function LogBox({ entries }) {
  const lines = entries || []
  return (
    <div className="log-box">
      {lines.length === 0 && <div className="log-line muted">暂无日志…</div>}
      {lines.map((e, i) => {
        const ok = e.status === 'SUCCESS'
        const err = e.status === 'FAILED' || e.status === 'ERROR'
        const cls = ok ? 'ok' : err ? 'err' : ''
        return (
          <div key={i} className={`log-line ${cls}`}>
            [{e.agent}] {e.action} · {e.details}
          </div>
        )
      })}
    </div>
  )
}

// ECharts 封装（懒初始化 + 自动 resize）
export function Chart({ option, height = 260 }) {
  const ref = useRef(null)
  const chartRef = useRef(null)
  useEffect(() => {
    if (!ref.current) return
    if (!chartRef.current) chartRef.current = echarts.init(ref.current)
    chartRef.current.setOption(option, true)
  }, [option])
  useEffect(() => {
    const onResize = () => chartRef.current && chartRef.current.resize()
    window.addEventListener('resize', onResize)
    return () => {
      window.removeEventListener('resize', onResize)
      if (chartRef.current) { chartRef.current.dispose(); chartRef.current = null }
    }
  }, [])
  return <div ref={ref} style={{ height }} />
}
