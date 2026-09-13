import { useState } from 'react'
import GermplasmPage from './pages/Germplasm.jsx'
import MatingsPage from './pages/Matings.jsx'
import PedigreePage from './pages/Pedigree.jsx'
import TrialsPage from './pages/Trials.jsx'
import StatsPage from './pages/Stats.jsx'
import RevisionsPage from './pages/Revisions.jsx'
import TracePanel from './components/TracePanel.jsx'

const TABS = [
  ['stats', '家系筛选'],
  ['germplasm', '材料'],
  ['matings', '交配'],
  ['pedigree', '谱系'],
  ['trials', '试验小区'],
  ['revisions', '亲本修订'],
]

export default function App() {
  const [tab, setTab] = useState('stats')
  const [traceCode, setTraceCode] = useState(null)

  const openTrace = (code) => setTraceCode(code)

  return (
    <div className="app">
      <header>
        <h1>育种谱系与家系筛选 <small>（演示数据均为虚构植物）</small></h1>
        <nav>
          {TABS.map(([key, label]) => (
            <button
              key={key}
              className={tab === key ? 'active' : ''}
              onClick={() => setTab(key)}
            >
              {label}
            </button>
          ))}
        </nav>
      </header>
      <main>
        {tab === 'stats' && <StatsPage onTrace={openTrace} />}
        {tab === 'germplasm' && <GermplasmPage onTrace={openTrace} />}
        {tab === 'matings' && <MatingsPage />}
        {tab === 'pedigree' && <PedigreePage onTrace={openTrace} />}
        {tab === 'trials' && <TrialsPage />}
        {tab === 'revisions' && <RevisionsPage />}
      </main>
      {traceCode && (
        <TracePanel code={traceCode} onClose={() => setTraceCode(null)} />
      )}
    </div>
  )
}
