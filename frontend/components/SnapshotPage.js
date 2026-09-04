'use client'

import { useEffect, useMemo, useState } from 'react'
import { api } from './Api'

const boards = ['科创板', '创业板', '中小板', '主板']

function boardForCode(code = '') {
  if (/^(688|689)/.test(code)) return '科创板'
  if (/^(300|301)/.test(code)) return '创业板'
  if (/^(002|003)/.test(code)) return '中小板'
  return '主板'
}

export default function SnapshotPage({ kind }) {
  const isTrend = kind === 'trend'
  const [dates, setDates] = useState([])
  const [selected, setSelected] = useState('')
  const [activeBoard, setActiveBoard] = useState(boards[0])
  const [snapshot, setSnapshot] = useState({ items: [] })
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const load = date => {
    setLoading(true)
    setError('')
    api(`/${kind}/${date ? `history?date=${date}` : 'latest'}`)
      .then(setSnapshot)
      .catch(error => setError(error.message))
      .finally(() => setLoading(false))
  }

  useEffect(() => {
    api(`/${kind}/dates`)
      .then(result => {
        const list = result.dates || []
        const first = list[0]?.trade_date || ''
        setDates(list)
        setSelected(first)
        load(first)
      })
      .catch(error => {
        setError(error.message)
        setLoading(false)
      })
  }, [kind])

  const visibleItems = useMemo(() => {
    if (isTrend) return snapshot.items
    return snapshot.items.filter(item => (item.board || boardForCode(item.code)) === activeBoard)
  }, [activeBoard, isTrend, snapshot.items])

  const average = !isTrend && visibleItems.length
    ? visibleItems.reduce((sum, item) => sum + (item.mktcap_yi || 0), 0) / visibleItems.length
    : null

  const chooseDate = event => {
    setSelected(event.target.value)
    load(event.target.value)
  }

  return <>
    <h1 className="sr-only">{isTrend ? '趋势向上' : '微盘股筛选'}</h1>
    <section className="search-card">
      <div className="microcap-toolbar">
        <label className="history-label">历史结果
          <select value={selected} onChange={chooseDate} disabled={!dates.length}>
            {dates.map(date => <option key={date.trade_date}>{date.trade_date}</option>)}
          </select>
        </label>
      </div>
      <p className="microcap-note">数据由独立 Python 采集任务每 6 小时更新。</p>
    </section>
    {!isTrend && <div className="board-tabs" role="tablist" aria-label="板块">
      {boards.map(board => <button
        key={board}
        type="button"
        role="tab"
        aria-selected={activeBoard === board}
        className={`board-tab ${activeBoard === board ? 'active' : ''}`}
        onClick={() => setActiveBoard(board)}
      >{board}</button>)}
    </div>}
    {error ? <p className="error">{error}</p> : loading ? <p className="loading">加载中…</p> : visibleItems.length ? <>
      <div className="results-summary">
        <span><strong>{snapshot.trade_date}</strong> 日{isTrend ? '趋势向上股票（MA20 连续上行）' : `${activeBoard}总市值最低 10 只`}</span>
        {average != null && <span>平均总市值 <strong>{average.toFixed(2)} 亿</strong></span>}
      </div>
      <div className="table-wrap"><table><thead><tr>
        <th>排名</th><th>代码</th><th>名称</th>
        {isTrend ? <><th>现价</th><th>换手率</th><th>MA20</th></> : <th>总市值</th>}
      </tr></thead><tbody>{visibleItems.map(item => <tr key={item.code}>
        <td>{item.rank}</td><td>{item.code}</td><td>{item.name}</td>
        {isTrend ? <><td>{item.price ?? '—'}</td><td>{item.turnover == null ? '—' : `${item.turnover}%`}</td><td>{item.ma20 ?? '—'}</td></> : <td>{item.mktcap_yi == null ? '—' : `${item.mktcap_yi} 亿`}</td>}
      </tr>)}</tbody></table></div>
    </> : <section className="empty-state"><div className="empty-icon">📉</div><p>该板块暂无数据。</p></section>}
  </>
}
