import { useEffect, useState } from 'react'
import { api } from '../api.js'

/** 交配登记：自交/杂交分别建模；父本可未知；环校验错误直接展示。 */
export default function MatingsPage() {
  const [events, setEvents] = useState([])
  const [form, setForm] = useState({
    type: 'CROSS', female_code: '', male_code: '', season: '',
    offspring_names: '', offspring_codes: '',
  })
  const [msg, setMsg] = useState('')
  const [err, setErr] = useState('')

  const load = () => api.get('/matings').then(setEvents).catch((e) => setErr(e.message))
  useEffect(() => { load() }, [])

  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value })

  const submit = async (e) => {
    e.preventDefault()
    setMsg(''); setErr('')
    try {
      const created = await api.post('/matings', {
        type: form.type,
        female_code: form.female_code.trim(),
        male_code: form.male_code.trim() || null, // 留空 = 未知父本
        season: form.season,
        offspring_names: form.offspring_names.split(/[\s,，]+/).filter(Boolean),
        offspring_codes: form.offspring_codes.split(/[\s,，]+/).filter(Boolean),
      })
      setMsg(`已登记 ${created.code}，后代 ${created.offspring.length} 个`)
      setForm({ ...form, female_code: '', male_code: '', offspring_names: '', offspring_codes: '' })
      load()
    } catch (e2) { setErr(e2.message) } // 如“后代不能成为祖先”
  }

  return (
    <div>
      <h2>交配事件</h2>
      <form onSubmit={submit} className="card">
        <div className="inline-form">
          <label>类型
            <select value={form.type} onChange={set('type')}>
              <option value="CROSS">杂交（不同亲本）</option>
              <option value="SELF">自交（同一亲本）</option>
            </select>
          </label>
          <input placeholder="母本编号，如 GM-0001" value={form.female_code}
                 onChange={set('female_code')} required />
          <input placeholder={form.type === 'SELF' ? '自交无需填父本' : '父本编号（未知则留空，不伪造）'}
                 value={form.male_code} onChange={set('male_code')}
                 disabled={form.type === 'SELF'} />
          <input placeholder="季节，如 2026-春" value={form.season} onChange={set('season')} />
        </div>
        <div className="inline-form">
          <input placeholder="新后代名称（空格分隔，允许与已有材料重名）"
                 value={form.offspring_names} onChange={set('offspring_names')} style={{ flex: 1 }} />
          <input placeholder="或挂接已有材料编号（补录历史谱系）"
                 value={form.offspring_codes} onChange={set('offspring_codes')} style={{ flex: 1 }} />
          <button type="submit">登记交配</button>
        </div>
        <p className="hint">
          规则：自交父母本必须相同；杂交父母本必须不同；禁止把后代登记为其祖先的后代（成环）。
        </p>
      </form>
      {msg && <p className="msg">{msg}</p>}
      {err && <p className="error">{err}</p>}
      <table>
        <thead>
          <tr><th>事件</th><th>类型</th><th>母本</th><th>父本</th><th>季节</th><th>后代</th></tr>
        </thead>
        <tbody>
          {events.map((e) => (
            <tr key={e.code}>
              <td><code>{e.code}</code></td>
              <td>{e.type === 'SELF' ? '自交' : '杂交'}</td>
              <td>{e.female.name}（{e.female.code}）</td>
              <td>{e.male ? `${e.male.name}（${e.male.code}）` : <span className="badge missing">未知</span>}</td>
              <td>{e.season}</td>
              <td>{e.offspring.map((o) => `${o.name}(${o.code},G${o.generation})`).join('、')}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
