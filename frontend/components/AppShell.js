'use client'
import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { useEffect, useState } from 'react'
import { api, clearToken, getToken } from './Api'

export default function AppShell({ children }) {
  const pathname = usePathname(); const [dark,setDark] = useState(false); const [loggedIn,setLoggedIn] = useState(false); const [pv,setPv] = useState({today:0,total:0})
  useEffect(() => { const value=localStorage.getItem('theme')==='dark'; setDark(value); document.documentElement.dataset.theme=value?'dark':'light'; setLoggedIn(Boolean(getToken())) }, [])
  useEffect(() => { api('/pv',{method:'POST'}).then(setPv).catch(()=>{}) }, [pathname])
  const toggle=()=>{const value=!dark;setDark(value);document.documentElement.dataset.theme=value?'dark':'light';localStorage.setItem('theme',value?'dark':'light')}
  const logout=async()=>{await api('/auth/logout',{method:'POST'}).catch(()=>{});clearToken();location.href='/login'}
  const links=[['/','股东查询'],['/microcap','微盘股'],['/trend','趋势向上'],['/sector','右侧品种']]
  return <div className="app-shell"><header className="nav"><div className="nav-inner"><div className="nav-brand"><span className="brand-mark">▦</span><span>工具箱</span></div><nav className="nav-links">{links.map(([href,label])=><Link key={href} href={href} className={`nav-link ${pathname===href?'active':''}`}>{label}</Link>)}</nav><div className="nav-actions">{loggedIn?<button className="nav-link" onClick={logout}>退出</button>:<Link href="/login" className="nav-link">登录</Link>}<button className="theme-toggle" onClick={toggle}>{dark?'☀️':'🌙'}</button></div></div></header><main className="main">{children}</main><footer className="footer">今日访问 {pv.today} · 累计访问 {pv.total}</footer></div>
}
