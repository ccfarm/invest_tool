import { DatabaseSync } from 'node:sqlite'
import crypto from 'node:crypto'
import fs from 'node:fs'
import path from 'node:path'

const dbPath = process.env.DB_PATH || path.join(process.cwd(), '..', 'backend', 'data', 'shareholders.db')
fs.mkdirSync(path.dirname(dbPath), { recursive: true })
const db = new DatabaseSync(dbPath)
db.exec(`PRAGMA journal_mode=WAL; PRAGMA busy_timeout=30000; PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS stocks(code TEXT PRIMARY KEY,name TEXT NOT NULL,market TEXT);
CREATE TABLE IF NOT EXISTS shareholders(id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT NOT NULL UNIQUE);
CREATE TABLE IF NOT EXISTS holdings(id INTEGER PRIMARY KEY AUTOINCREMENT,stock_code TEXT NOT NULL REFERENCES stocks(code),shareholder_id INTEGER NOT NULL REFERENCES shareholders(id),hold_num INTEGER NOT NULL,hold_num_ratio REAL,change_text TEXT,end_date TEXT NOT NULL,holder_rank INTEGER,updated_at TEXT NOT NULL,UNIQUE(stock_code,shareholder_id,end_date));
CREATE INDEX IF NOT EXISTS idx_holdings_end_date ON holdings(end_date DESC);
CREATE INDEX IF NOT EXISTS idx_holdings_shareholder ON holdings(shareholder_id);
CREATE TABLE IF NOT EXISTS crawl_state(stock_code TEXT PRIMARY KEY,last_crawled_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS pv_stats(date TEXT PRIMARY KEY,count INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS microcap_blacklist(code TEXT PRIMARY KEY,name TEXT,reason TEXT,created_at TEXT);
CREATE TABLE IF NOT EXISTS microcap_snapshots(id INTEGER PRIMARY KEY AUTOINCREMENT,trade_date TEXT UNIQUE,created_at TEXT,items TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS trend_snapshots(id INTEGER PRIMARY KEY AUTOINCREMENT,trade_date TEXT UNIQUE,created_at TEXT,items TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY AUTOINCREMENT,username TEXT NOT NULL UNIQUE,password_hash TEXT NOT NULL,created_at TEXT);
CREATE TABLE IF NOT EXISTS sessions(token_hash TEXT PRIMARY KEY,username TEXT NOT NULL,created_at TEXT,expires_at TEXT);`)

const now = () => new Date().toISOString()
const today = () => new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Shanghai', year:'numeric', month:'2-digit', day:'2-digit' }).format(new Date())
const hashToken = token => crypto.createHash('sha256').update(token).digest('hex')
export function initUser(){const username=process.env.AUTH_USERNAME||'test';const exists=db.prepare('SELECT 1 FROM users WHERE username=?').get(username);if(!exists){const iterations=600000,salt=crypto.randomBytes(16),digest=crypto.pbkdf2Sync(process.env.AUTH_PASSWORD||'test',salt,iterations,32,'sha256');db.prepare('INSERT INTO users(username,password_hash,created_at) VALUES(?,?,?)').run(username,`pbkdf2_sha256$${iterations}$${salt.toString('hex')}$${digest.toString('hex')}`,now())}}
export function login(username,password){initUser();const row=db.prepare('SELECT password_hash FROM users WHERE username=?').get(username);if(!row)return null;const[,iterations,salt,expected]=row.password_hash.split('$');const actual=crypto.pbkdf2Sync(password,Buffer.from(salt,'hex'),Number(iterations),32,'sha256');if(expected.length!==actual.length*2||!crypto.timingSafeEqual(Buffer.from(expected,'hex'),actual))return null;const token=crypto.randomBytes(32).toString('base64url'),created=now(),expires=new Date(Date.now()+Number(process.env.TOKEN_TTL_SECONDS||604800)*1000).toISOString();db.prepare('INSERT INTO sessions(token_hash,username,created_at,expires_at) VALUES(?,?,?,?)').run(hashToken(token),username,created,expires);return{token,username}}
export function usernameFor(token){if(!token)return null;return db.prepare('SELECT username FROM sessions WHERE token_hash=? AND expires_at>?').get(hashToken(token),now())?.username||null}
export function logout(token){if(token)db.prepare('DELETE FROM sessions WHERE token_hash=?').run(hashToken(token))}
export function pv(increment=false){const date=today();if(increment)db.prepare('INSERT INTO pv_stats(date,count) VALUES(?,1) ON CONFLICT(date) DO UPDATE SET count=count+1').run(date);return{today:Number(db.prepare('SELECT COALESCE(SUM(count),0) n FROM pv_stats WHERE date=?').get(date).n),total:Number(db.prepare('SELECT COALESCE(SUM(count),0) n FROM pv_stats').get().n)}}
export function search(q,page,pageSize){q=q.trim();const numeric=/^\d+$/.test(q);const where=numeric?'h.stock_code=?':'h.shareholder_id IN (SELECT id FROM shareholders WHERE name LIKE ?)';const param=numeric?q:`%${q}%`;const total=Number(db.prepare(`SELECT COUNT(*) n FROM holdings h WHERE ${where}`).get(param).n);const rows=db.prepare(`SELECT h.stock_code,s.name stock_name,h.shareholder_id,sh.name holder_name,h.hold_num,h.hold_num_ratio,h.change_text,h.end_date FROM holdings h JOIN stocks s ON s.code=h.stock_code JOIN shareholders sh ON sh.id=h.shareholder_id WHERE ${where} ORDER BY h.end_date DESC LIMIT ? OFFSET ?`).all(param,pageSize,(page-1)*pageSize);const previous=db.prepare('SELECT hold_num FROM holdings WHERE stock_code=? AND shareholder_id=? AND end_date<? ORDER BY end_date DESC LIMIT 1');return{query:q,page,page_size:pageSize,total,items:rows.map(r=>{const old=previous.get(r.stock_code,r.shareholder_id,r.end_date);return{...r,change:old?Number(r.hold_num)-Number(old.hold_num):null}})}}
function snapshot(table,date){const row=date?db.prepare(`SELECT trade_date,created_at,items FROM ${table} WHERE trade_date=?`).get(date):db.prepare(`SELECT trade_date,created_at,items FROM ${table} ORDER BY trade_date DESC LIMIT 1`).get();return row?{...row,items:JSON.parse(row.items)}:{trade_date:null,created_at:null,items:[]}}
export const microcap=d=>snapshot('microcap_snapshots',d)
export const trend=d=>snapshot('trend_snapshots',d)
export function dates(table){return{dates:db.prepare(`SELECT trade_date,created_at FROM ${table} ORDER BY trade_date DESC LIMIT 20`).all()}}
