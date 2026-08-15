import { useEffect, useState } from 'react'
import Dashboard from './pages/Dashboard.jsx'
import NewResearch from './pages/NewResearch.jsx'
import Report from './pages/Report.jsx'
import Metrics from './pages/Metrics.jsx'
import Settings from './pages/Settings.jsx'

function parseHash() {
  const h = window.location.hash.replace(/^#/, '') || '/'
  const parts = h.split('/').filter(Boolean)
  if (parts.length === 0) return { view: 'dashboard' }
  if (parts[0] === 'new') return { view: 'new' }
  if (parts[0] === 'report') return { view: 'report', id: parts[1] }
  if (parts[0] === 'metrics') return { view: 'metrics' }
  if (parts[0] === 'settings') return { view: 'settings' }
  return { view: 'dashboard' }
}

export default function App() {
  const [route, setRoute] = useState(parseHash())

  useEffect(() => {
    const onHash = () => setRoute(parseHash())
    window.addEventListener('hashchange', onHash)
    return () => window.removeEventListener('hashchange', onHash)
  }, [])

  function go(path) {
    window.location.hash = path
  }

  const navCls = (view) => (view === route.view ? 'nav-item active' : 'nav-item')

  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark">E</div>
          <div className="brand-text">
            <div className="brand-name">Eco-Research</div>
            <div className="brand-sub">多智能体投研工作台</div>
          </div>
        </div>

        <nav className="nav">
          <div className={navCls('dashboard')} onClick={() => go('/')}>
            <Icon.Grid /><span>工作台</span>
          </div>
          <div className={navCls('new')} onClick={() => go('/new')}>
            <Icon.FilePlus /><span>新建调研</span>
          </div>
          <div className={navCls('metrics')} onClick={() => go('/metrics')}>
            <Icon.Database /><span>指标库</span>
          </div>
          <div className={navCls('settings')} onClick={() => go('/settings')}>
            <Icon.Settings /><span>设置</span>
          </div>
        </nav>

        <div className="sidebar-footer">
          <span className="version-dot" />
          <span>v1.0.0</span>
        </div>
      </aside>
      <main className="main">
        {route.view === 'dashboard' && <Dashboard go={go} />}
        {route.view === 'new' && <NewResearch go={go} />}
        {route.view === 'report' && <Report id={route.id} />}
        {route.view === 'metrics' && <Metrics />}
        {route.view === 'settings' && <Settings />}
      </main>
    </div>
  )
}

// 侧边栏导航图标（Lucide 风格，stroke=currentColor 跟随文字变色）
const Icon = {
  Grid: () => (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <rect x="3" y="3" width="7" height="7" rx="1.5" /><rect x="14" y="3" width="7" height="7" rx="1.5" />
      <rect x="3" y="14" width="7" height="7" rx="1.5" /><rect x="14" y="14" width="7" height="7" rx="1.5" />
    </svg>
  ),
  FilePlus: () => (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
      <path d="M14 2v6h6" /><line x1="12" y1="12" x2="12" y2="18" /><line x1="9" y1="15" x2="15" y2="15" />
    </svg>
  ),
  Database: () => (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <ellipse cx="12" cy="5" rx="9" ry="3" />
      <path d="M3 5v14a9 3 0 0 0 18 0V5" /><path d="M3 12a9 3 0 0 0 18 0" />
    </svg>
  ),
  Settings: () => (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="3" />
      <path d="M12 1v4M12 19v4M4.2 4.2l2.8 2.8M17 17l2.8 2.8M1 12h4M19 12h4M4.2 19.8L7 17M17 7l2.8-2.8" />
    </svg>
  ),
}
