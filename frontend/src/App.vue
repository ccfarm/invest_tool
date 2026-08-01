<template>
  <div class="app-shell">
    <header class="nav">
      <div class="nav-inner">
        <div class="nav-brand">
          <span class="brand-mark">▦</span>
          <span class="brand-name">工具箱</span>
        </div>
        <nav class="nav-links">
          <router-link to="/" class="nav-link active">股东查询</router-link>
          <router-link to="/microcap" class="nav-link">微盘股</router-link>
        </nav>
        <div class="nav-actions">
          <router-link v-if="!hasToken" to="/login" class="nav-link">登录</router-link>
          <button v-else type="button" class="nav-link" @click="handleLogout">退出</button>
          <button type="button" class="theme-toggle" :title="isDark ? '切换到浅色' : '切换到深色'" @click="toggleTheme">
            {{ isDark ? '☀️' : '🌙' }}
          </button>
        </div>
      </div>
    </header>

    <main class="main">
      <router-view />
    </main>

    <footer class="footer">
      今日访问 {{ pv.today }} · 累计访问 {{ pv.total }}
    </footer>
  </div>
</template>

<script setup>
import { ref, onMounted, watch } from 'vue'
import { useRoute } from 'vue-router'
import { clearToken, getToken, logout, recordPv } from './api'

const isDark = ref(false)
const pv = ref({ today: 0, total: 0 })
const hasToken = ref(Boolean(getToken()))
const route = useRoute()

function applyTheme() {
  document.documentElement.dataset.theme = isDark.value ? 'dark' : 'light'
  localStorage.setItem('theme', isDark.value ? 'dark' : 'light')
}

function toggleTheme() {
  isDark.value = !isDark.value
  applyTheme()
}

async function bumpPv() {
  try {
    pv.value = await recordPv()
  } catch {
    // 统计失败不影响使用
  }
}

async function handleLogout() {
  try {
    await logout()
  } catch {
    // 即使接口失败也清除本地 token
  }
  clearToken()
  window.location.href = '/login'
}

onMounted(() => {
  isDark.value = localStorage.getItem('theme') === 'dark'
  applyTheme()
  bumpPv()
})

watch(() => route.path, bumpPv)
</script>
