<script setup>
import { ref } from 'vue'
import { clearToken, getToken, login, logout, setToken } from '../api'

const username = ref('')
const password = ref('')
const error = ref('')
const loading = ref(false)
const loggedIn = ref(Boolean(getToken()))

async function submit() {
  if (!username.value.trim() || !password.value) {
    error.value = '请输入用户名和密码'
    return
  }
  loading.value = true
  error.value = ''
  try {
    const r = await login(username.value.trim(), password.value)
    setToken(r.token)
    window.location.href = '/'
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

async function doLogout() {
  try {
    await logout()
  } catch {
    // ignore
  }
  clearToken()
  window.location.href = '/login'
}
</script>

<template>
  <div>
    <h1 class="sr-only">登录</h1>
    <section class="search-card login-card">
      <template v-if="!loggedIn">
        <label class="search-label" for="login-username">用户名</label>
        <input
          id="login-username"
          v-model="username"
          class="search-input"
          type="text"
          autocomplete="username"
          placeholder="请输入用户名"
        />
        <label class="search-label" for="login-password">密码</label>
        <input
          id="login-password"
          v-model="password"
          class="search-input"
          type="password"
          autocomplete="current-password"
          placeholder="请输入密码"
          @keyup.enter="submit"
        />
        <p v-if="error" class="error">{{ error }}</p>
        <button class="btn" :disabled="loading" @click="submit">
          {{ loading ? '登录中…' : '登录' }}
        </button>
      </template>
      <template v-else>
        <p class="login-note">已登录，当前功能无需登录也可使用。</p>
        <button class="btn" @click="doLogout">退出登录</button>
      </template>
    </section>
  </div>
</template>
