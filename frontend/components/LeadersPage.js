'use client'

import { useEffect, useState } from 'react'
import { api } from './Api'

const settings = {
  strong: { title: '最近强势', description: '沪深北 A 股近20个交易日涨幅最大的20只股票。' },
  newhigh: { title: '新高', description: '前复权收盘价突破此前五年最高收盘价，过滤上市未满三年的股票；上市三至五年按上市以来历史比较。' },
}

export default function LeadersPage({ kind }) {
  const [snapshot, setSnapshot] = useState({ items: [] })
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const config = settings[kind]

  useEffect(() => {
    let active = true
    setLoading(true)
    setError('')
    api(`/${kind}/latest`)
      .then(value => { if (active) setSnapshot(value) })
      .catch(error => { if (active) setError(error.message) })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [kind])

  return <>
    <h1 className="sr-only">{config.title}</h1>
    <section className="search-card sector-intro">
      <div><h2>{config.title}</h2><p>{config.description}</p></div>
      {snapshot.trade_date && <time>数据日期 {snapshot.trade_date}</time>}
    </section>
    {error ? <p className="error" role="alert">{error}</p> : loading ? <p className="loading">加载中…</p> : <>
      <div className="results-summary"><span>共 <strong>{snapshot.items.length}</strong> 只 · 按近1个月涨幅降序</span><span>每日收盘后更新 · 月涨幅使用前复权价格</span></div>
      {snapshot.items.length ? <div className="table-wrap"><table><thead><tr>
        <th>排名</th><th>代码</th><th>名称</th><th>板块 / 行业</th><th>主要概念</th><th>题材</th><th>近1个月涨幅</th>
      </tr></thead><tbody>{snapshot.items.map(item => <tr key={item.code}>
        <td>{item.rank}</td><td><a className="code-link" href={`https://quote.eastmoney.com/${item.code}.html`} target="_blank" rel="noopener noreferrer">{item.code}</a></td>
        <td>{item.name}</td><td>{item.board}{item.industry && item.industry !== '-' ? ` / ${item.industry}` : ''}</td>
        <td>{item.main_concepts?.join('、') || '暂无数据'}</td>
        <td>{item.themes?.length ? <details><summary>{item.themes.length} 个题材</summary><p className="leaders-themes">{item.themes.join('、')}</p></details> : '暂无数据'}</td>
        <td><strong className={item.month_change_pct >= 0 ? 'market-up' : 'market-down'}>{item.month_change_pct >= 0 ? '+' : ''}{item.month_change_pct.toFixed(2)}%</strong></td>
      </tr>)}</tbody></table></div> : <section className="empty-state"><p>{snapshot.trade_date ? '当日没有符合条件的股票。' : '数据尚未生成，请等待收盘后采集。'}</p></section>}
      <p className="leaders-note">主要概念展示同花顺概念列表前三项；题材展示完整概念列表，不代表实时热点或涨停原因。</p>
    </>}
  </>
}
