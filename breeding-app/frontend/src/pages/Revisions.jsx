import { useEffect, useState } from 'react'
import { api } from '../api.js'

const STATUS_LABEL = {
  DRAFT: '草案', CONFIRMED: '已确认', REJECTED: '已驳回', SUPERSEDED: '已被取代',
}
const FIELD_LABEL = { FEMALE: '母本', MALE: '父本' }

const parentTxt = (p) => (p ? `${p.name}（${p.code}）` : '未知')

/** 亲本修订：草案 → 证据+确认人 → 生效；发布版本与待确认重算。 */
export default function RevisionsPage() {
  const [revisions, setRevisions] = useState([])
  const [trials, setTrials] = useState([])
  const [trialId, setTrialId] = useState(null)
  const [pubs, setPubs] = useState([])
  const [recalcs, setRecalcs] = useState([])
  const [detail, setDetail] = useState(null) // 某修订的影响分析
  const [form, setForm] = useState({
    event_code: '', field: 'MALE', new_parent_code: '', evidence: '', proposer: '',
  })
  const [confirmer, setConfirmer] = useState({}) // code → 确认人
  const [pubForm, setPubForm] = useState({ trait: '', published_by: '' })
  const [msg, setMsg] = useState('')
  const [err, setErr] = useState('')

  const load = () => {
    api.get('/revisions').then(setRevisions).catch((e) => setErr(e.message))
    api.get('/recalc').then(setRecalcs).catch((e) => setErr(e.message))
  }
  useEffect(() => {
    load()
    api.get('/trials').then((ts) => {
      setTrials(ts)
      if (ts.length) setTrialId((id) => id ?? ts[0].id)
    }).catch((e) => setErr(e.message))
  }, [])

  useEffect(() => {
    if (!trialId) return
    api.get(`/trials/${trialId}/publications`).then(setPubs).catch((e) => setErr(e.message))
  }, [trialId, recalcs])

  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value })

  const createDraft = async (e) => {
    e.preventDefault()
    setMsg(''); setErr('')
    try {
      const created = await api.post('/revisions', {
        ...form,
        new_parent_code: form.new_parent_code.trim() || null,
      })
      setMsg(`已创建草案 ${created.code}（草案不影响任何结论，需确认后生效）`)
      setDetail(created)
      setForm({ ...form, event_code: '', new_parent_code: '', evidence: '' })
      load()
    } catch (e2) { setErr(e2.message) }
  }

  const showImpact = async (code) => {
    setErr('')
    try { setDetail(await api.get(`/revisions/${code}`)) }
    catch (e2) { setErr(e2.message) }
  }

  const confirm = async (code) => {
    setMsg(''); setErr('')
    try {
      const r = await api.post(`/revisions/${code}/confirm`, {
        confirmer: confirmer[code] || '',
      })
      const rc = r.recalc_proposals.length
        ? `；形成待确认重算 ${r.recalc_proposals.join('、')}`
        : ''
      setMsg(`修订 ${code} 已确认生效${rc}`)
      load()
    } catch (e2) { setErr(e2.message) } // 世代循环路径 / 来源未知 / 矛盾草案
  }

  const reject = async (code) => {
    setMsg(''); setErr('')
    try {
      await api.post(`/revisions/${code}/reject`, { resolver: '' })
      setMsg(`草案 ${code} 已驳回`)
      load()
    } catch (e2) { setErr(e2.message) }
  }

  const publish = async () => {
    setMsg(''); setErr('')
    try {
      const p = await api.post(`/trials/${trialId}/publish`, pubForm)
      setMsg(`已发布版本 v${p.version}（不可变快照）`)
      load()
    } catch (e2) { setErr(e2.message) }
  }

  const resolveRecalc = async (code, action) => {
    setMsg(''); setErr('')
    const resolver = window.prompt(action === 'approve' ? '批准人：' : '驳回人：')
    if (!resolver) return
    try {
      const r = await api.post(`/recalc/${code}/${action}`, { resolver })
      setMsg(action === 'approve'
        ? `重算 ${code} 已批准，形成发布版本 v${r.publication.version}`
        : `重算 ${code} 已驳回，旧发布版本继续有效`)
      load()
    } catch (e2) { setErr(e2.message) }
  }

  return (
    <div>
      <h2>亲本修订</h2>
      <p className="hint">
        原交配记录永不被覆盖；草案需证据与确认人（≠提出人）才生效；
        造成世代循环或来源未知的修订会被阻止并指出路径。
      </p>

      <form onSubmit={createDraft} className="card">
        <h3>新建修订草案</h3>
        <div className="inline-form">
          <input placeholder="交配事件号，如 ME-0001" value={form.event_code}
                 onChange={set('event_code')} required />
          <select value={form.field} onChange={set('field')}>
            <option value="MALE">修订父本</option>
            <option value="FEMALE">修订母本</option>
          </select>
          <input placeholder="新亲本编号（留空=修订为未知）"
                 value={form.new_parent_code} onChange={set('new_parent_code')} />
          <input placeholder="提出人" value={form.proposer}
                 onChange={set('proposer')} required />
        </div>
        <div className="inline-form">
          <input placeholder="证据（确认时必填，如标签照片/记录编号）"
                 value={form.evidence} onChange={set('evidence')} style={{ flex: 1 }} />
          <button type="submit">创建草案</button>
        </div>
      </form>
      {msg && <p className="msg">{msg}</p>}
      {err && <p className="error">{err}</p>}

      <h3>修订列表</h3>
      <table>
        <thead>
          <tr>
            <th>编号</th><th>事件</th><th>字段</th><th>原亲本</th><th>新亲本</th>
            <th>证据</th><th>提出人</th><th>确认人</th><th>状态</th><th>操作</th>
          </tr>
        </thead>
        <tbody>
          {revisions.map((r) => (
            <tr key={r.code}>
              <td><code>{r.code}</code></td>
              <td>{r.event_code}</td>
              <td>{FIELD_LABEL[r.field]}</td>
              <td>{parentTxt(r.old_parent)}</td>
              <td>{parentTxt(r.new_parent)}</td>
              <td>{r.evidence || <span className="badge missing">缺证据</span>}</td>
              <td>{r.proposer}</td>
              <td>{r.confirmer || '—'}</td>
              <td>
                <span className={`badge rev-${r.status.toLowerCase()}`}>
                  {STATUS_LABEL[r.status]}
                </span>
                {r.conflicts_with.length > 0 && (
                  <span className="badge dead">矛盾：{r.conflicts_with.join('、')}</span>
                )}
              </td>
              <td>
                <button onClick={() => showImpact(r.code)}>影响</button>
                {r.status === 'DRAFT' && (
                  <>
                    <input
                      placeholder="确认人" style={{ width: 70 }}
                      value={confirmer[r.code] || ''}
                      onChange={(e) => setConfirmer({ ...confirmer, [r.code]: e.target.value })}
                    />
                    <button onClick={() => confirm(r.code)}>确认</button>
                    <button onClick={() => reject(r.code)}>驳回</button>
                  </>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      {detail && (
        <div className="card">
          <h3>
            修订 {detail.code} 影响分析
            <button className="close-inline" onClick={() => setDetail(null)}>收起</button>
          </h3>
          {detail.blocking_issue && (
            <p className="error">若确认将被阻止：{detail.blocking_issue}</p>
          )}
          <p>
            <b>谱系受影响后代（{detail.impact.pedigree_affected.length}）：</b>
            {detail.impact.pedigree_affected
              .map((g) => `${g.name}(${g.code},G${g.generation})`).join('、') || '无'}
          </p>
          <p>
            <b>家系统计受影响后代（{detail.impact.stats_affected.length}）：</b>
            {detail.impact.stats_affected
              .map((g) => `${g.name}(${g.code})`).join('、') || '无'}
          </p>
          <p>
            <b>涉及试验：</b>
            {detail.impact.affected_trials.map((t) => t.name).join('、') || '无'}
          </p>
        </div>
      )}

      <h3>发布版本（按旧家系分组的结果原样保留）</h3>
      <div className="inline-form">
        <label>试验
          <select value={trialId ?? ''} onChange={(e) => setTrialId(Number(e.target.value))}>
            {trials.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
          </select>
        </label>
        <input placeholder="性状，如 株高cm" value={pubForm.trait}
               onChange={(e) => setPubForm({ ...pubForm, trait: e.target.value })} />
        <input placeholder="发布人" value={pubForm.published_by}
               onChange={(e) => setPubForm({ ...pubForm, published_by: e.target.value })} />
        <button onClick={publish} disabled={!pubForm.trait || !pubForm.published_by}>
          发布当前统计为新版本
        </button>
      </div>
      <table>
        <thead>
          <tr><th>性状</th><th>版本</th><th>发布人</th><th>发布时间</th></tr>
        </thead>
        <tbody>
          {pubs.map((p) => (
            <tr key={p.id}>
              <td>{p.trait}</td><td>v{p.version}</td>
              <td>{p.published_by}</td><td>{p.published_at.slice(0, 19).replace('T', ' ')}</td>
            </tr>
          ))}
        </tbody>
      </table>

      <h3>待确认的重算（批准后才成为新发布版本；不改动人工淘汰/保留决定）</h3>
      <table>
        <thead>
          <tr>
            <th>编号</th><th>试验</th><th>性状</th><th>基于版本</th>
            <th>触发修订</th><th>状态</th><th>操作</th>
          </tr>
        </thead>
        <tbody>
          {recalcs.map((r) => (
            <tr key={r.code}>
              <td><code>{r.code}</code></td>
              <td>{r.trial_name}</td>
              <td>{r.trait}</td>
              <td>v{r.based_version}</td>
              <td>{r.revision_code}</td>
              <td><span className={`badge rev-${r.status.toLowerCase()}`}>{r.status}</span></td>
              <td>
                {r.status === 'PENDING' && (
                  <>
                    <button onClick={() => resolveRecalc(r.code, 'approve')}>批准</button>
                    <button onClick={() => resolveRecalc(r.code, 'reject')}>驳回</button>
                  </>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
