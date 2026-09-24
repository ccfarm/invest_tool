'use client'

import { useEffect, useState } from 'react'
import { api } from './Api'

const show = value => value == null ? '—' : Number(value).toFixed(2)
const marketClass = value => Number(value) > 0 ? 'market-up' : Number(value) < 0 ? 'market-down' : ''

export default function ValuecapPage() {
  const [snapshot, setSnapshot] = useState({items: []})
  const [dates, setDates] = useState([])
  const [selected, setSelected] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const load = date => {
    setLoading(true); setError('')
    api(`/valuecap/${date ? `history?date=${date}` : 'latest'}`)
      .then(setSnapshot).catch(err => setError(err.message)).finally(() => setLoading(false))
  }

  useEffect(() => {
    api('/valuecap/dates').then(result => {
      const list = result.dates || []
      const first = list[0]?.trade_date || ''
      setDates(list); setSelected(first); load(first)
    }).catch(err => {setError(err.message); setLoading(false)})
  }, [])

  return <>
    <h1 className="sr-only">低价小盘稳健榜</h1>
    <section className="search-card sector-intro valuecap-intro">
      <div><h2>低价小盘稳健榜</h2><p>从沪深 A 股中筛选2—15元、20—100亿元市值且成交活跃的股票，排除 ST、退市及公告风险后，展示每日综合得分最高的10只。</p></div>
      <label className="history-label">历史结果<select value={selected} onChange={event => {setSelected(event.target.value); load(event.target.value)}} disabled={!dates.length}>{dates.map(date => <option key={date.trade_date}>{date.trade_date}</option>)}</select></label>
    </section>
    <p className="microcap-note">评分由低价25分、小盘25分、面值安全20分、流动性15分、估值质量15分组成，仅作量化筛选参考。</p>
    {error ? <p className="error">{error}</p> : loading ? <p className="loading">加载中…</p> : snapshot.items.length ? <>
      <div className="results-summary"><span><strong>{snapshot.trade_date}</strong> 综合得分 Top 10</span><span>无法完成公告风险核验的股票不会入选</span></div>
      <div className="table-wrap"><table><thead><tr>
        <th>排名</th><th>代码</th><th>名称</th><th>得分</th><th>现价</th><th>涨跌幅</th><th>总市值</th><th>成交额</th><th>市盈率</th><th>市净率</th>
      </tr></thead><tbody>{snapshot.items.map(item => <tr key={item.code}>
        <td>{item.rank}</td><td><a className="code-link" href={`https://quote.eastmoney.com/${item.code.startsWith('6') ? 'sh' : 'sz'}${item.code}.html`} target="_blank" rel="noopener noreferrer">{item.code}</a></td><td>{item.name}</td><td><strong className="score-pill" title={`低价 ${item.score_parts.low_price} · 小盘 ${item.score_parts.small_cap} · 面值安全 ${item.score_parts.price_safety} · 流动性 ${item.score_parts.liquidity} · 估值质量 ${item.score_parts.valuation_quality}`}>{show(item.score)}</strong></td><td>{show(item.price)}</td><td><span className={marketClass(item.change_pct)}>{item.change_pct > 0 ? '+' : ''}{show(item.change_pct)}%</span></td><td>{show(item.mktcap_yi)}亿</td><td>{show(item.amount_wan)}万</td><td>{show(item.pe)}</td><td>{show(item.pb)}</td>
      </tr>)}</tbody></table></div>
    </> : <section className="empty-state"><div className="empty-icon">🛡️</div><p>今日榜单正在生成，请稍后刷新。</p></section>}
  </>
}
