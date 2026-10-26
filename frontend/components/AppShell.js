'use client'
import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { useEffect, useState } from 'react'
import { api, clearToken, getToken } from './Api'

export default function AppShell({ children }) {
  const [menuOpen, setMenuOpen] = useState(false)
  const pathname = usePathname(); const [dark,setDark] = useState(false); const [loggedIn,setLoggedIn] = useState(false); const [pv,setPv] = useState({today:0,total:0})
  useEffect(() => { const value=localStorage.getItem('theme')==='dark'; setDark(value); document.documentElement.dataset.theme=value?'dark':'light'; setLoggedIn(Boolean(getToken())) }, [])
  useEffect(() => { setMenuOpen(false); api('/pv',{method:'POST'}).then(setPv).catch(()=>{}) }, [pathname])
  const toggle=()=>{const value=!dark;setDark(value);document.documentElement.dataset.theme=value?'dark':'light';localStorage.setItem('theme',value?'dark':'light')}
  const logout=async()=>{await api('/auth/logout',{method:'POST'}).catch(()=>{});clearToken();location.href='/login'}
  const links=[['/','股东查询'],['/microcap','微盘股'],['/valuecap','低价稳健'],['/strong','最近强势'],['/newhigh','新高'],['/trend','趋势向上'],['/dividend','红利低波'],['/sector','右侧品种'],['/oversold','超跌板块']]
  return (
    <div className="app-shell">
      <button
        className="menu-toggle"
        aria-label={menuOpen ? '关闭导航' : '打开导航'}
        aria-expanded={menuOpen}
        aria-controls="sidebar-navigation"
        onClick={() => setMenuOpen(!menuOpen)}
      >
        {menuOpen ? '✕ 关闭' : '☰ 导航'}
      </button>
      {menuOpen && (
        <button className="nav-backdrop" aria-label="关闭导航" onClick={() => setMenuOpen(false)} />
      )}
      <header
        id="sidebar-navigation"
        className={`nav ${menuOpen ? 'is-open' : ''}`}
        onKeyDown={event => {
          if (event.key === 'Escape') {
            setMenuOpen(false)
            document.querySelector('.menu-toggle')?.focus()
          }
        }}
      >
        <div className="nav-inner">
          <div className="nav-brand">
            <span className="brand-mark" aria-hidden="true">▦</span><span>工具箱</span>
          </div>
          <nav className="nav-links" aria-label="主导航">
            {links.map(([href, label]) => {
              const active = pathname === href || (href === '/' && pathname === '/results')
              return (
                <Link
                  key={href}
                  href={href}
                  aria-current={active ? 'page' : undefined}
                  onClick={() => setMenuOpen(false)}
                  className={`nav-link ${active ? 'active' : ''}`}
                >
                  {label}
                </Link>
              )
            })}
          </nav>
          <div className="nav-actions">
            {loggedIn
              ? <button className="nav-link" onClick={logout}>退出</button>
              : <Link href="/login" className="nav-link" onClick={() => setMenuOpen(false)}>登录</Link>}
            <button
              className="theme-toggle"
              onClick={toggle}
              aria-label={dark ? '切换浅色主题' : '切换深色主题'}
            >
              {dark ? '☀️' : '🌙'}
            </button>
          </div>
        </div>
      </header>
      <div className="app-content">
        <main className="main">{children}</main>
        <footer className="footer">今日访问 {pv.today} · 累计访问 {pv.total}</footer>
      </div>
    </div>
  )
}
