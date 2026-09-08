'use client'

import { useEffect, useState } from 'react'
import { api } from './Api'

const pct = value => {
  const number = Number(value)
  const cls = number > 0 ? 'market-up' : number < 0 ? 'market-down' : ''
  return <span className={cls}>{number > 0 ? '+' : ''}{number.toFixed(2)}%</span>
}

export default function DividendPage() {
  const [snapshot, setSnapshot] = useState({items: []})
  const [dates, setDates] = useState([])
  const [selected, setSelected] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const load = date => {
    setLoading(true); setError('')
    api(`/dividend/${date ? `history?date=${date}` : 'latest'}`)
      .then(setSnapshot).catch(error => setError(error.message)).finally(() => setLoading(false))
  }

  useEffect(() => {
    api('/dividend/dates').then(result => {
      const list = result.dates || []
      const first = list[0]?.trade_date || ''
      setDates(list); setSelected(first); load(first)
    }).catch(error => {setError(error.message); setLoading(false)})
  }, [])

  const chooseDate = event => {setSelected(event.target.value); load(event.target.value)}
  return <>
    <h1 className="sr-only">红利低波</h1>
    <section className="search-card sector-intro dividend-intro">
      <div><h2>红利低波</h2><p>连续5个完整财年现金分红、平均股息率不低于3%，从高股息候选中精选近60日波动率较低的股票。</p></div>
      <label className="history-label">历史结果<select value={selected} onChange={chooseDate} disabled={!dates.length}>{dates.map(date => <option key={date.trade_date}>{date.trade_date}</option>)}</select></label>
    </section>
    {error ? <p className="error">{error}</p> : loading ? <p className="loading">加载中…</p> : snapshot.items.length ? <>
      <div className="results-summary"><span><strong>{snapshot.trade_date}</strong> 红利低波精选</span><span>RSI 分位按近250日，股价分位按近5年</span></div>
      <div className="table-wrap"><table><thead><tr>
        <th>排名</th><th>代码</th><th>名称</th><th>现价</th><th>五年平均股息率</th><th>当日涨幅</th><th>近20日</th><th>近60日</th><th>RSI(14)</th><th>RSI分位</th><th>股价分位</th><th>60日波动率</th>
      </tr></thead><tbody>{snapshot.items.map(item => <tr key={item.code}>
        <td>{item.rank}</td><td><a className="code-link" href={`https://quote.eastmoney.com/${item.code.startsWith('6') ? 'sh' : 'sz'}${item.code}.html`} target="_blank" rel="noopener noreferrer">{item.code}</a></td><td>{item.name}</td><td>{item.price.toFixed(2)}</td><td><strong>{item.avg_dividend_yield.toFixed(2)}%</strong></td><td>{pct(item.change_day)}</td><td>{pct(item.change_20d)}</td><td>{pct(item.change_60d)}</td><td>{item.rsi.toFixed(2)}</td><td>{item.rsi_percentile.toFixed(1)}%</td><td>{item.price_percentile.toFixed(1)}%</td><td>{item.volatility_60d.toFixed(2)}%</td>
      </tr>)}</tbody></table></div>
    </> : <section className="empty-state"><div className="empty-icon">💰</div><p>今日数据尚未生成。</p></section>}
  </>
}
