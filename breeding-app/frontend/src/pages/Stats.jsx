import { useEffect, useState } from 'react'
import { api } from '../api.js'

/** 家系筛选：按“小区×重复”口径的统计表，点击后代可回溯交配与观测来源。 */
export default function StatsPage({ onTrace }) {
  const [trials, setTrials] = useState([])
  const [trialId, setTrialId] = useState(null)
  const [traits, setTraits] = useState([])
  const [trait, setTrait] = useState('')
  const [stats, setStats] = useState(null)
  const [err, setErr] = useState('')
  const [familyDetail, setFamilyDetail] = useState(null) // 选中的家系后代

  useEffect(() => {
    api.get('/trials').then((ts) => {
      setTrials(ts)
      if (ts.length && !trialId) setTrialId(ts[0].id)
    }).catch((e) => setErr(e.message))
  }, []) // eslint-disable-line

  useEffect(() => {
    if (!trialId) return
    api.get(`/stats/trial/${trialId}/traits`).then((ts) => {
      setTraits(ts)
      if (ts.length) setTrait((t) => t || ts[0])
    }).catch((e) => setErr(e.message))
  }, [trialId])

  useEffect(() => {
    if (!trialId || !trait) return
    setErr('')
    api.get(`/stats/trial/${trialId}/families?trait=${encodeURIComponent(trait)}`)
      .then(setStats).catch((e) => setErr(e.message))
  }, [trialId, trait])

  const showFamily = async (code) => {
    setErr('')
    try { setFamilyDetail(await api.get(`/matings/${code}`)) }
    catch (e) { setErr(e.message) }
  }

  const fmt = (v) => (v === null || v === undefined ? '—' : Number(v).toFixed(2))

  return (
    <div>
      <h2>家系筛选依据</h2>
      <div className="inline-form">
        <label>试验
          <select value={trialId ?? ''} onChange={(e) => setTrialId(Number(e.target.value))}>
            {trials.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
          </select>
        </label>
        <label>性状
          <select value={trait} onChange={(e) => setTrait(e.target.value)}>
            {traits.map((t) => <option key={t} value={t}>{t}</option>)}
          </select>
        </label>
      </div>
      {err && <p className="error">{err}</p>}
      <p className="hint">
        口径：同株多次测定先在株内平均；家系均值为小区均值的平均（不按株数加权）；
        未测/死亡不进均值只计数；真实零值正常参与均值。
      </p>
      {stats && (
        <table>
          <thead>
            <tr>
              <th>排名</th><th>家系</th><th>均值</th><th>重复数</th><th>小区数</th>
              <th>已测株</th><th>未测</th><th>死亡</th><th>真零值</th>
              <th>各重复均值</th><th></th>
            </tr>
          </thead>
          <tbody>
            {stats.families.map((f, i) => (
              <tr key={f.family_code}>
                <td>{f.mean === null ? '—' : i + 1}</td>
                <td>{f.family_label}</td>
                <td><b>{fmt(f.mean)}</b></td>
                <td>{f.n_replicates}</td>
                <td>{f.n_plots}</td>
                <td>{f.n_plants_measured}</td>
                <td>{f.n_missing > 0 && <span className="badge missing">{f.n_missing}</span>}{f.n_missing === 0 && 0}</td>
                <td>{f.n_dead > 0 && <span className="badge dead">{f.n_dead}</span>}{f.n_dead === 0 && 0}</td>
                <td>{f.n_true_zero}</td>
                <td>{f.replicates.map((r) => `R${r.replicate}=${fmt(r.mean)}`).join('，')}</td>
                <td><button onClick={() => showFamily(f.family_code)}>查看后代</button></td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {familyDetail && (
        <div className="card">
          <h3>
            家系 {familyDetail.code}：{familyDetail.female.name}（{familyDetail.female.code}）
            {familyDetail.type === 'SELF'
              ? ' 自交'
              : ` × ${familyDetail.male ? `${familyDetail.male.name}（${familyDetail.male.code}）` : '未知父本'}`}
            <button className="close-inline" onClick={() => setFamilyDetail(null)}>收起</button>
          </h3>
          <table>
            <thead><tr><th>后代编号</th><th>名称</th><th>世代</th><th></th></tr></thead>
            <tbody>
              {familyDetail.offspring.map((o) => (
                <tr key={o.code}>
                  <td><code>{o.code}</code></td>
                  <td>{o.name}</td>
                  <td>{o.generation}</td>
                  <td><button onClick={() => onTrace(o.code)}>回溯交配与观测来源</button></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
