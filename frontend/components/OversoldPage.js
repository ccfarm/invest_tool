'use client'

import { useEffect, useState } from 'react'
import { api } from './Api'

export default function OversoldPage() {
  const [snapshot, setSnapshot] = useState({ items: [] })
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    api('/oversold/latest')
      .then(setSnapshot)
      .catch(error => setError(error.message))
      .finally(() => setLoading(false))
  }, [])

  return <>
    <h1 className="sr-only">超跌板块</h1>
    <section className="search-card sector-intro">
      <div><h2>超跌板块</h2><p>当前 RSI(14) 落在自身最近200个交易日倒数5%分位的东方财富行业板块。</p></div>
      {snapshot.trade_date && <time>数据日期 {snapshot.trade_date}</time>}
    </section>
    {error ? <p className="error">{error}</p> : loading ? <p className="loading">加载中…</p> : snapshot.items.length ? <>
      <div className="results-summary">
        <span>仅统计成分股数量<strong>大于10只</strong>的行业</span>
        <span>每日收盘后计算一次</span>
      </div>
      <div className="table-wrap"><table><thead><tr>
        <th>排名</th><th>行业板块</th><th>当前 RSI(14)</th><th>历史5%阈值</th><th>当前分位</th><th>成分股数</th>
      </tr></thead><tbody>{snapshot.items.map(item => <tr key={item.code}>
        <td>{item.rank}</td>
        <td><a className="code-link" href={item.url} target="_blank" rel="noopener noreferrer">{item.name}</a></td>
        <td><strong className="market-down">{item.rsi.toFixed(2)}</strong></td>
        <td>{item.threshold.toFixed(2)}</td><td>{item.percentile.toFixed(1)}%</td><td>{item.stock_count}</td>
      </tr>)}</tbody></table></div>
    </> : <section className="empty-state"><div className="empty-icon">📉</div><p>当前没有行业进入历史倒数5%分位，或今日数据尚未生成。</p></section>}
  </>
}
