import { useEffect, useState } from 'react'
import { api } from '../api.js'

const STATUS_LABEL = { MEASURED: '已测', MISSING: '未测', DEAD: '死亡' }

/** 来源回溯面板：展示某材料的交配来源与全部观测留痕。 */
export default function TracePanel({ code, onClose }) {
  const [data, setData] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    setData(null)
    setError('')
    api.get(`/germplasm/${code}/trace`).then(setData).catch((e) => setError(e.message))
  }, [code])

  return (
    <div className="drawer-mask" onClick={onClose}>
      <div className="drawer" onClick={(e) => e.stopPropagation()}>
        <button className="close" onClick={onClose}>×</button>
        <h2>来源回溯：{code}</h2>
        {error && <p className="error">{error}</p>}
        {!data && !error && <p>加载中…</p>}
        {data && (
          <>
            <section>
              <h3>材料身份</h3>
              <p>
                <b>{data.germplasm.name}</b>（稳定编号 {data.germplasm.code}，
                第 {data.germplasm.generation} 代）
              </p>
            </section>
            <section>
              <h3>交配来源</h3>
              {data.origin ? (
                <>
                  <table>
                    <tbody>
                      <tr><td>交配事件</td><td>{data.origin.event_code}</td></tr>
                      <tr><td>类型</td><td>{data.origin.type === 'SELF' ? '自交' : '杂交'}</td></tr>
                      <tr><td>母本（现行）</td><td>{data.origin.female.name}（{data.origin.female.code}）</td></tr>
                      <tr>
                        <td>父本（现行）</td>
                        <td>
                          {data.origin.male
                            ? `${data.origin.male.name}（${data.origin.male.code}）`
                            : '未知（未伪造补全）'}
                        </td>
                      </tr>
                      <tr>
                        <td>原始记录</td>
                        <td>
                          {data.origin.female_original.name}（{data.origin.female_original.code}）×{' '}
                          {data.origin.male_original
                            ? `${data.origin.male_original.name}（${data.origin.male_original.code}）`
                            : '未知父本'}
                        </td>
                      </tr>
                      <tr><td>季节</td><td>{data.origin.season || '—'}</td></tr>
                      <tr>
                        <td>同胞</td>
                        <td>{data.origin.siblings.length ? data.origin.siblings.join('、') : '无'}</td>
                      </tr>
                    </tbody>
                  </table>
                  {data.origin.revisions.length > 0 && (
                    <>
                      <h4>亲本修订记录（原交配事实不被覆盖）</h4>
                      <table>
                        <thead>
                          <tr>
                            <th>编号</th><th>字段</th><th>原亲本</th><th>新亲本</th>
                            <th>状态</th><th>证据</th><th>提出人</th><th>确认人</th>
                          </tr>
                        </thead>
                        <tbody>
                          {data.origin.revisions.map((r) => (
                            <tr key={r.code}>
                              <td><code>{r.code}</code></td>
                              <td>{r.field === 'MALE' ? '父本' : '母本'}</td>
                              <td>{r.old_parent ? `${r.old_parent.name}(${r.old_parent.code})` : '未知'}</td>
                              <td>{r.new_parent ? `${r.new_parent.name}(${r.new_parent.code})` : '未知'}</td>
                              <td><span className={`badge rev-${r.status.toLowerCase()}`}>{r.status}</span></td>
                              <td>{r.evidence || '—'}</td>
                              <td>{r.proposer}</td>
                              <td>{r.confirmer || '—'}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </>
                  )}
                </>
              ) : (
                <p>基础材料，无来源交配事件。</p>
              )}
            </section>
            <section>
              <h3>观测记录（{data.observations.length} 条）</h3>
              {data.observations.length === 0 ? (
                <p>暂无观测。</p>
              ) : (
                <table>
                  <thead>
                    <tr>
                      <th>试验</th><th>小区</th><th>重复</th><th>株号</th>
                      <th>性状</th><th>状态</th><th>数值</th>
                      <th>来源</th><th>补录</th><th>更新时间</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.observations.map((o) => (
                      <tr key={o.id}>
                        <td>{o.trial}</td>
                        <td>{o.plot_label}</td>
                        <td>{o.replicate}</td>
                        <td>{o.plant_tag}</td>
                        <td>{o.trait}</td>
                        <td><span className={`badge ${o.status.toLowerCase()}`}>{STATUS_LABEL[o.status]}</span></td>
                        <td>{o.value === null ? '—' : o.value}</td>
                        <td>{o.source || '—'}</td>
                        <td>{o.backfilled ? '是' : '否'}</td>
                        <td>{o.updated_at.slice(0, 19).replace('T', ' ')}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </section>
          </>
        )}
      </div>
    </div>
  )
}
