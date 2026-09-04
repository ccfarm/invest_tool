'use client'

import { useEffect, useState } from 'react'
import { api } from './Api'

export default function SectorSidebar() {
  const [snapshot, setSnapshot] = useState({ items: [] })
  const [error, setError] = useState('')

  useEffect(() => {
    api('/sectors/latest').then(setSnapshot).catch(error => setError(error.message))
  }, [])

  return <aside className="sector-sidebar" aria-labelledby="sector-title">
    <div className="sector-head">
      <div><h2 id="sector-title">近期强势板块</h2><p>近10日涨幅前20 · 按强势股占比排序</p></div>
      {snapshot.trade_date && <time>{snapshot.trade_date.slice(5)}</time>}
    </div>
    {error ? <p className="sector-message">暂时无法加载</p> : snapshot.items.length ?
      <ol className="sector-list">{snapshot.items.map(item => <li key={item.code}>
        <a href={item.url} target="_blank" rel="noopener noreferrer" title={`查看东方财富 ${item.name} 板块`}>
          <span className="sector-rank">{item.rank}</span>
          <span className="sector-name">{item.name}</span>
          <span className="sector-ratio">{item.strong_ratio.toFixed(1)}%</span>
          <span className={`sector-return ${item.return_10d >= 0 ? 'up' : 'down'}`}>{item.return_10d >= 0 ? '+' : ''}{item.return_10d.toFixed(2)}%</span>
          <span className="sector-count">{item.strong_count}/{item.valid_count}</span>
        </a>
      </li>)}</ol> : <p className="sector-message">收盘后生成当日榜单</p>}
    <div className="sector-legend"><span>强势股：MA5 &gt; MA10 &gt; MA20</span><span>右侧为近10日涨幅</span></div>
  </aside>
}
