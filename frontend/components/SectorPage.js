'use client'

import { useEffect, useState } from 'react'
import { api } from './Api'

export default function SectorPage() {
  const [snapshot, setSnapshot] = useState({ items: [] })
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    api('/sectors/latest')
      .then(setSnapshot)
      .catch(error => setError(error.message))
      .finally(() => setLoading(false))
  }, [])

  return <>
    <h1 className="sr-only">右侧品种</h1>
    <section className="search-card sector-intro">
      <div><h2>右侧品种</h2><p>东方财富行业板块近10个交易日涨幅前20，按强势个股占比从高到低排列。</p></div>
      {snapshot.trade_date && <time>数据日期 {snapshot.trade_date}</time>}
    </section>
    {error ? <p className="error">{error}</p> : loading ? <p className="loading">加载中…</p> : snapshot.items.length ? <>
      <div className="results-summary">
        <span>强势个股口径：<strong>MA5 &gt; MA10 &gt; MA20</strong></span>
        <span>每日收盘后计算一次</span>
      </div>
      <div className="table-wrap"><table><thead><tr>
        <th>排名</th><th>行业板块</th><th>强势个股占比</th><th>强势数 / 有效数</th><th>近10日涨幅</th>
      </tr></thead><tbody>{snapshot.items.map(item => <tr key={item.code}>
        <td>{item.rank}</td>
        <td><a className="code-link" href={item.url} target="_blank" rel="noopener noreferrer">{item.name}</a></td>
        <td><strong className="sector-ratio">{item.strong_ratio.toFixed(1)}%</strong></td>
        <td>{item.strong_count} / {item.valid_count}</td>
        <td className={item.return_10d >= 0 ? 'market-up' : 'market-down'}>{item.return_10d >= 0 ? '+' : ''}{item.return_10d.toFixed(2)}%</td>
      </tr>)}</tbody></table></div>
    </> : <section className="empty-state"><div className="empty-icon">📊</div><p>收盘后生成当日右侧品种榜单。</p></section>}
  </>
}
