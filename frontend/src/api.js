const BASE = '/api'
const TOKEN_KEY = 'auth_token'

export function getToken() {
  return localStorage.getItem(TOKEN_KEY)
}

export function setToken(token) {
  localStorage.setItem(TOKEN_KEY, token)
}

export function clearToken() {
  localStorage.removeItem(TOKEN_KEY)
}

function authHeaders() {
  const token = getToken()
  return token ? { Authorization: `Bearer ${token}` } : {}
}

export async function login(username, password) {
  const resp = await fetch(`${BASE}/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password }),
  })
  if (!resp.ok) {
    throw new Error('用户名或密码错误')
  }
  return resp.json()
}

export async function fetchMe() {
  const resp = await fetch(`${BASE}/auth/me`, { headers: authHeaders() })
  if (!resp.ok) {
    throw new Error(`请求失败：${resp.status}`)
  }
  return resp.json()
}

export async function logout() {
  const resp = await fetch(`${BASE}/auth/logout`, {
    method: 'POST',
    headers: authHeaders(),
  })
  if (!resp.ok) {
    throw new Error(`请求失败：${resp.status}`)
  }
}

export async function searchHoldings(q, page = 1, pageSize = 20) {
  const params = new URLSearchParams({ q, page: String(page), page_size: String(pageSize) })
  const resp = await fetch(`${BASE}/search?${params}`)
  if (!resp.ok) {
    throw new Error(`请求失败：${resp.status}`)
  }
  return resp.json()
}

export async function recordPv() {
  const resp = await fetch(`${BASE}/pv`, { method: 'POST' })
  if (!resp.ok) {
    throw new Error(`请求失败：${resp.status}`)
  }
  return resp.json()
}

export async function refreshMicrocap() {
  const resp = await fetch(`${BASE}/microcap/refresh`, { method: 'POST' })
  if (!resp.ok) {
    throw new Error(`请求失败：${resp.status}`)
  }
  return resp.json()
}

export async function getLatestMicrocap() {
  const resp = await fetch(`${BASE}/microcap/latest`)
  if (!resp.ok) {
    throw new Error(`请求失败：${resp.status}`)
  }
  return resp.json()
}

export async function getMicrocapDates() {
  const resp = await fetch(`${BASE}/microcap/dates`)
  if (!resp.ok) {
    throw new Error(`请求失败：${resp.status}`)
  }
  return resp.json()
}

export async function getMicrocapHistory(date) {
  const resp = await fetch(`${BASE}/microcap/history?date=${encodeURIComponent(date)}`)
  if (!resp.ok) {
    throw new Error(`请求失败：${resp.status}`)
  }
  return resp.json()
}

export async function refreshTrend() {
  const resp = await fetch(`${BASE}/trend/refresh`, { method: 'POST' })
  if (!resp.ok) {
    throw new Error(`请求失败：${resp.status}`)
  }
  return resp.json()
}

export async function getLatestTrend() {
  const resp = await fetch(`${BASE}/trend/latest`)
  if (!resp.ok) {
    throw new Error(`请求失败：${resp.status}`)
  }
  return resp.json()
}

export async function getTrendDates() {
  const resp = await fetch(`${BASE}/trend/dates`)
  if (!resp.ok) {
    throw new Error(`请求失败：${resp.status}`)
  }
  return resp.json()
}

export async function getTrendHistory(date) {
  const resp = await fetch(`${BASE}/trend/history?date=${encodeURIComponent(date)}`)
  if (!resp.ok) {
    throw new Error(`请求失败：${resp.status}`)
  }
  return resp.json()
}

export async function getTrendKline(code) {
  const resp = await fetch(`${BASE}/trend/kline?code=${encodeURIComponent(code)}`)
  if (!resp.ok) {
    throw new Error(`请求失败：${resp.status}`)
  }
  return resp.json()
}
