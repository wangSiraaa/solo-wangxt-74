import { useEffect, useState } from 'react'
import { api } from '../api.js'

const STATUS_LABEL = { MEASURED: '已测', MISSING: '未测', DEAD: '死亡' }

/** 试验小区：小区→观测录入与补录。区分未测/死亡/真实零值。 */
export default function TrialsPage() {
  const [trials, setTrials] = useState([])
  const [trialId, setTrialId] = useState(null)
  const [plots, setPlots] = useState([])
  const [plotId, setPlotId] = useState(null)
  const [obs, setObs] = useState([])
  const [msg, setMsg] = useState('')
  const [err, setErr] = useState('')
  const [newObs, setNewObs] = useState({
    plant_tag: '', germplasm_code: '', trait: '株高cm', status: 'MEASURED', value: '', source: '',
  })
  const [backfill, setBackfill] = useState({}) // obsId → {value, source}

  useEffect(() => {
    api.get('/trials').then((ts) => {
      setTrials(ts)
      if (ts.length && !trialId) setTrialId(ts[0].id)
    }).catch((e) => setErr(e.message))
  }, []) // eslint-disable-line

  useEffect(() => {
    if (!trialId) return
    api.get(`/trials/${trialId}/plots`).then((ps) => {
      setPlots(ps)
      setPlotId(ps[0]?.id ?? null)
    }).catch((e) => setErr(e.message))
  }, [trialId])

  const loadObs = () => {
    if (!plotId) { setObs([]); return }
    api.get(`/observations/by-plot/${plotId}`).then(setObs).catch((e) => setErr(e.message))
  }
  useEffect(() => { loadObs() }, [plotId]) // eslint-disable-line

  const submitObs = async (e) => {
    e.preventDefault()
    setMsg(''); setErr('')
    try {
      await api.post('/observations', {
        plot_id: plotId,
        plant_tag: newObs.plant_tag,
        germplasm_code: newObs.germplasm_code.trim() || null, // 标签丢失则留空
        trait: newObs.trait,
        status: newObs.status,
        value: newObs.status === 'MEASURED' ? Number(newObs.value) : null,
        source: newObs.source,
      })
      setMsg('观测已录入')
      setNewObs({ ...newObs, plant_tag: '', value: '' })
      loadObs()
    } catch (e2) { setErr(e2.message) }
  }

  const doBackfill = async (o, targetStatus) => {
    setMsg(''); setErr('')
    const entry = backfill[o.id] || {}
    try {
      await api.patch(`/observations/${o.id}`, {
        status: targetStatus,
        value: targetStatus === 'MEASURED' ? Number(entry.value) : null,
        source: entry.source || '',
      })
      setMsg(`观测 #${o.id} 已补录`)
      loadObs()
    } catch (e2) { setErr(e2.message) }
  }

  const plot = plots.find((p) => p.id === plotId)

  return (
    <div>
      <h2>试验小区与观测</h2>
      <div className="inline-form">
        <label>试验
          <select value={trialId ?? ''} onChange={(e) => setTrialId(Number(e.target.value))}>
            {trials.map((t) => <option key={t.id} value={t.id}>{t.name}（{t.season}）</option>)}
          </select>
        </label>
        <label>小区
          <select value={plotId ?? ''} onChange={(e) => setPlotId(Number(e.target.value))}>
            {plots.map((p) => (
              <option key={p.id} value={p.id}>
                {p.label}（重复{p.replicate}，家系 {p.family_code ?? '未指定'}）
              </option>
            ))}
          </select>
        </label>
      </div>

      {plot && (
        <form onSubmit={submitObs} className="card">
          <h3>录入观测（小区 {plot.label}）</h3>
          <div className="inline-form">
            <input placeholder="株号，如 P07" value={newObs.plant_tag} required
                   onChange={(e) => setNewObs({ ...newObs, plant_tag: e.target.value })} />
            <input placeholder="材料编号（标签丢失留空）" value={newObs.germplasm_code}
                   onChange={(e) => setNewObs({ ...newObs, germplasm_code: e.target.value })} />
            <input placeholder="性状" value={newObs.trait} required
                   onChange={(e) => setNewObs({ ...newObs, trait: e.target.value })} />
            <select value={newObs.status}
                    onChange={(e) => setNewObs({ ...newObs, status: e.target.value })}>
              <option value="MEASURED">已测</option>
              <option value="MISSING">未测</option>
              <option value="DEAD">死亡</option>
            </select>
            {newObs.status === 'MEASURED' && (
              <input type="number" step="any" placeholder="数值（真实零值填 0）" required
                     value={newObs.value}
                     onChange={(e) => setNewObs({ ...newObs, value: e.target.value })} />
            )}
            <input placeholder="来源/录入人" value={newObs.source}
                   onChange={(e) => setNewObs({ ...newObs, source: e.target.value })} />
            <button type="submit">录入</button>
          </div>
        </form>
      )}
      {msg && <p className="msg">{msg}</p>}
      {err && <p className="error">{err}</p>}

      <table>
        <thead>
          <tr>
            <th>株号</th><th>材料</th><th>性状</th><th>状态</th><th>数值</th>
            <th>来源</th><th>补录</th><th>操作</th>
          </tr>
        </thead>
        <tbody>
          {obs.map((o) => (
            <tr key={o.id}>
              <td>{o.plant_tag}</td>
              <td>{o.germplasm_code ?? <span className="badge missing">标签丢失</span>}</td>
              <td>{o.trait}</td>
              <td><span className={`badge ${o.status.toLowerCase()}`}>{STATUS_LABEL[o.status]}</span></td>
              <td>{o.value === null ? '—' : o.value}</td>
              <td>{o.source || '—'}</td>
              <td>{o.backfilled ? '是' : '否'}</td>
              <td>
                {o.status === 'MISSING' && (
                  <span className="backfill">
                    <input type="number" step="any" placeholder="补录值"
                      value={backfill[o.id]?.value ?? ''}
                      onChange={(e) => setBackfill({ ...backfill, [o.id]: { ...backfill[o.id], value: e.target.value } })} />
                    <input placeholder="来源（必填）"
                      value={backfill[o.id]?.source ?? ''}
                      onChange={(e) => setBackfill({ ...backfill, [o.id]: { ...backfill[o.id], source: e.target.value } })} />
                    <button onClick={() => doBackfill(o, 'MEASURED')}>补录</button>
                    <button onClick={() => doBackfill(o, 'DEAD')}>标记死亡</button>
                  </span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
