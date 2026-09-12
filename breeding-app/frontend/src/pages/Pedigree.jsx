import { useState } from 'react'
import { api } from '../api.js'

/** 谱系视图：祖先树 + 后代列表。未知亲本不构造节点，仅文字说明。 */
export default function PedigreePage({ onTrace }) {
  const [code, setCode] = useState('')
  const [data, setData] = useState(null)
  const [err, setErr] = useState('')

  const load = async (c) => {
    setErr(''); setData(null)
    try { setData(await api.get(`/germplasm/${c}/pedigree`)) }
    catch (e) { setErr(e.message) }
  }

  // child → [{parent, event, type}]
  const parentsOf = {}
  for (const e of data?.edges ?? []) {
    ;(parentsOf[e.child] = parentsOf[e.child] || []).push(e)
  }
  const info = {}
  for (const n of [data?.focus, ...(data?.ancestors ?? []), ...(data?.descendants ?? [])]) {
    if (n) info[n.code] = n
  }

  const renderNode = (c, depth) => {
    const n = info[c]
    if (!n || depth > 10) return null
    const parents = parentsOf[c] || []
    return (
      <li key={c}>
        <span className={c === data.focus.code ? 'focus-node' : ''}>
          {n.name}（{c}，G{n.generation}）
        </span>{' '}
        <button onClick={() => onTrace(c)}>回溯</button>
        {parents.length > 0 && (
          <ul>
            {parents.map((e) => (
              <span key={`${e.parent}-${e.event}`} className="edge-wrap">
                {renderNode(e.parent, depth + 1)}
              </span>
            ))}
          </ul>
        )}
      </li>
    )
  }

  return (
    <div>
      <h2>谱系查询</h2>
      <div className="inline-form">
        <input placeholder="材料编号，如 GM-0008" value={code}
               onChange={(e) => setCode(e.target.value)} />
        <button onClick={() => load(code.trim())}>查询</button>
      </div>
      {err && <p className="error">{err}</p>}
      {data && (
        <div className="pedigree">
          <section className="card">
            <h3>祖先（{data.ancestors.length}）</h3>
            {data.ancestors.length === 0
              ? <p>基础材料，无已知祖先。</p>
              : <ul className="tree">{renderNode(data.focus.code, 0)}</ul>}
            <p className="hint">
              未知亲本不构成节点、不会被伪造补全；半同胞家系只显示已知亲本一侧。
            </p>
          </section>
          <section className="card">
            <h3>后代（{data.descendants.length}）</h3>
            {data.descendants.length === 0 ? <p>暂无登记后代。</p> : (
              <ul>
                {data.descendants.map((d) => (
                  <li key={d.code}>
                    {d.name}（{d.code}，G{d.generation}）{' '}
                    <button onClick={() => onTrace(d.code)}>回溯</button>
                  </li>
                ))}
              </ul>
            )}
          </section>
        </div>
      )}
    </div>
  )
}
