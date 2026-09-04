'use client'
const TOKEN_KEY = 'auth_token'
export const getToken = () => typeof window === 'undefined' ? null : localStorage.getItem(TOKEN_KEY)
export const setToken = token => localStorage.setItem(TOKEN_KEY, token)
export const clearToken = () => localStorage.removeItem(TOKEN_KEY)
export async function api(path, options = {}) {
  const token = getToken()
  const response = await fetch(`/api${path}`, { ...options, headers: { ...(options.body ? {'Content-Type':'application/json'} : {}), ...(token ? {Authorization:`Bearer ${token}`} : {}), ...options.headers } })
  const body = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error(body.detail || `请求失败：${response.status}`)
  return body
}
