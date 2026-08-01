<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import QuickShareholders from '../components/QuickShareholders.vue'

const router = useRouter()
const keyword = ref('')
const searchInput = ref(null)

function submit() {
  const q = keyword.value.trim()
  if (!q) {
    alert('请输入股东姓名或 A 股代码')
    return
  }
  router.push({ path: '/results', query: { q } })
}

function quickSearch(q) {
  keyword.value = q
  searchInput.value?.focus()
}
</script>

<template>
  <div>
    <h1 class="sr-only">股东持股查询</h1>
    <section class="search-card">
      <label class="search-label" for="home-search">搜索股东</label>
      <form class="search-row" @submit.prevent="submit">
        <div class="search-input-wrap">
          <svg
            class="search-icon"
            width="16"
            height="16"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
            stroke-linecap="round"
            stroke-linejoin="round"
            aria-hidden="true"
          >
            <circle cx="11" cy="11" r="7"></circle>
            <line x1="21" y1="21" x2="16.65" y2="16.65"></line>
          </svg>
          <input
            id="home-search"
            ref="searchInput"
            v-model="keyword"
            class="search-input"
            type="text"
            placeholder="输入股东姓名或 A 股代码…"
          />
        </div>
        <button type="submit" class="btn">查询</button>
      </form>
    </section>

    <QuickShareholders @select="quickSearch" />

    <section class="empty-state">
      <div class="empty-icon">🔍</div>
      <p>在上方输入股东姓名或 A 股代码，即可查看相关持股信息与分析结果。</p>
    </section>
  </div>
</template>
