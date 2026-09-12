import { useEffect, useState } from 'react'
import { api } from '../api.js'

/** 材料列表：同名材料靠稳定编号区分；可登记基础材料。 */
export default function GermplasmPage({ onTrace }) {
  const [items, setItems] = useState([])
  const [search, setSearch] = useState('')
  const [name, setName] = useState('')
  const [generation, setGeneration] = useState(0)
  const [notes, setNotes] = useState('')
  const [msg, setMsg] = useState('')

  const load = () =>
    api.get(`/germplasm${search ? `?search=${encodeURIComponent(search)}` : ''}`)
      .then(setItems).catch((e) => setMsg(e.message))

  useEffect(() => { load() }, []) // eslint-disable-line

  const nameCounts = items.reduce((m, g) => {
    m[g.name] = (m[g.name] || 0) + 1
    return m
  }, {})

  const submit = async (e) => {
    e.preventDefault()
    setMsg('')
    try {
      const g = await api.post('/germplasm', {
        name, generation: Number(generation), notes,
      })
      setMsg(`已登记 ${g.name}，稳定编号 ${g.code}`)
      setName(''); setNotes('')
      load()
    } catch (err) { setMsg(err.message) }
  }

  return (
    <div>
      <h2>材料库</h2>
      <form onSubmit={submit} className="inline-form">
        <input placeholder="名称（允许与已有材料重名）" value={name}
               onChange={(e) => setName(e.target.value)} required />
        <input type="number" min="0" value={generation} title="世代"
               onChange={(e) => setGeneration(e.target.value)} style={{ width: 90 }} />
        <input placeholder="备注" value={notes} onChange={(e) => setNotes(e.target.value)} />
        <button type="submit">登记基础材料</button>
      </form>
      <div className="inline-form">
        <input placeholder="按名称或编号搜索" value={search}
               onChange={(e) => setSearch(e.target.value)} />
        <button onClick={load}>搜索</button>
      </div>
      {msg && <p className="msg">{msg}</p>}
      <table>
        <thead>
          <tr><th>稳定编号</th><th>名称</th><th>世代</th><th>备注</th><th></th></tr>
        </thead>
        <tbody>
          {items.map((g) => (
            <tr key={g.code}>
              <td><code>{g.code}</code></td>
              <td>
                {g.name}
                {nameCounts[g.name] > 1 && (
                  <span className="badge dup">同名×{nameCounts[g.name]}，以编号区分</span>
                )}
              </td>
              <td>{g.generation}</td>
              <td>{g.notes}</td>
              <td><button onClick={() => onTrace(g.code)}>回溯</button></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
