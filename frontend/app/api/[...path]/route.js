import { NextResponse } from 'next/server'
import { spawn } from 'node:child_process'
import path from 'node:path'
import { dates, login, logout, microcap, pv, search, sectors, trend, usernameFor } from '@/lib/db'

export const runtime = 'nodejs'; export const dynamic = 'force-dynamic'
const json=(body,status=200)=>NextResponse.json(body,{status})
const bearer=req=>(req.headers.get('authorization')||'').replace(/^Bearer\s+/i,'')
function crawler(command,args=[]){return new Promise((resolve,reject)=>{const backend=path.join(process.cwd(),'..','backend');const python=process.env.PYTHON_BIN||path.join(backend,'.venv','bin','python');const child=spawn(python,['-m','app.jobs',command,...args],{cwd:backend,env:process.env});let out='',err='';child.stdout.on('data',d=>out+=d);child.stderr.on('data',d=>err+=d);child.on('error',reject);child.on('close',code=>{if(code)reject(new Error(err||`Python exited ${code}`));else{try{resolve(JSON.parse(out))}catch(e){reject(new Error(`采集器返回无效数据: ${e.message}`))}}})})}
export async function GET(req,{params}){const p=(await params).path.join('/'),u=new URL(req.url);try{
  if(p==='health')return json({status:'ok'})
  if(p==='search'){const q=(u.searchParams.get('q')||'').slice(0,100),page=Math.max(1,Number(u.searchParams.get('page')||1)),size=Math.min(100,Math.max(1,Number(u.searchParams.get('page_size')||20)));if(!q)return json({detail:'q 必填'},422);return json(await search(q,page,size))}
  if(p==='pv')return json(await pv())
  if(p==='microcap/latest')return json(await microcap())
  if(p==='microcap/dates')return json(await dates('microcap_snapshots'))
  if(p==='microcap/history'){const value=await microcap(u.searchParams.get('date'));return value.trade_date?json(value):json({detail:'未找到快照'},404)}
  if(p==='trend/latest')return json(await trend())
  if(p==='trend/dates')return json(await dates('trend_snapshots'))
  if(p==='trend/history'){const value=await trend(u.searchParams.get('date'));return value.trade_date?json(value):json({detail:'未找到快照'},404)}
  if(p==='trend/kline')return json(await crawler('kline',[u.searchParams.get('code')||'']))
  if(p==='sectors/latest')return json(await sectors())
  if(p==='auth/me'){const username=await usernameFor(bearer(req));return username?json({username}):json({detail:'登录已过期，请重新登录'},401)}
  return json({detail:'Not found'},404)
}catch(e){return json({detail:e.message},500)}}
export async function POST(req,{params}){const p=(await params).path.join('/');try{
  if(p==='pv')return json(await pv(true))
  if(p==='auth/login'){const body=await req.json();const result=await login(body.username||'',body.password||'');return result?json(result):json({detail:'用户名或密码错误'},401)}
  if(p==='auth/logout'){const token=bearer(req);if(!await usernameFor(token))return json({detail:'未登录'},401);await logout(token);return json({ok:true})}
  if(p==='microcap/refresh')return json(await crawler('microcap'))
  if(p==='trend/refresh')return json(await crawler('trend'))
  if(p==='sectors/refresh')return json(await crawler('sector'))
  return json({detail:'Not found'},404)
}catch(e){return json({detail:e.message},500)}}
