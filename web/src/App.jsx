import { useEffect, useState } from 'react'
import Dashboard from './pages/Dashboard.jsx'
import NewResearch from './pages/NewResearch.jsx'
import Report from './pages/Report.jsx'
import Metrics from './pages/Metrics.jsx'

function parseHash() {
  const h = window.location.hash.replace(/^#/, '') || '/'
  const parts = h.split('/').filter(Boolean)
  if (parts.length === 0) return { view: 'dashboard' }
  if (parts[0] === 'new') return { view: 'new' }
  if (parts[0] === 'report') return { view: 'report', id: parts[1] }
  if (parts[0] === 'metrics') return { view: 'metrics' }
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
          <div>
            <div className="brand-name">Eco-Research</div>
            <div className="brand-sub">多智能体投研工作台</div>
          </div>
        </div>
        <div className={navCls('dashboard')} onClick={() => go('/')}>工作台</div>
        <div className={navCls('new')} onClick={() => go('/new')}>新建调研</div>
        <div className={navCls('metrics')} onClick={() => go('/metrics')}>指标库</div>
      </aside>
      <main className="main">
        {route.view === 'dashboard' && <Dashboard go={go} />}
        {route.view === 'new' && <NewResearch go={go} />}
        {route.view === 'report' && <Report id={route.id} />}
        {route.view === 'metrics' && <Metrics />}
      </main>
    </div>
  )
}
