<script setup>
import { ref, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { searchHoldings } from '../api'
import QuickShareholders from '../components/QuickShareholders.vue'

const route = useRoute()
const router = useRouter()

const keyword = ref(route.query.q || '')
const searchInput = ref(null)
const result = ref({ total: 0, page: 1, page_size: 20, items: [] })
const loading = ref(false)
const error = ref('')
const totalPages = ref(1)

function fmt(n) {
  return n == null ? '—' : n.toLocaleString('en-US')
}

function changeLabel(item) {
  if (item.change === null) return { text: '新进', cls: 'new' }
  if (item.change > 0) return { text: `+${fmt(item.change)}`, cls: 'up' }
  if (item.change < 0) return { text: `−${fmt(-item.change)}`, cls: 'down' }
  return { text: '0', cls: 'flat' }
}

async function load() {
  const q = keyword.value.trim()
  if (!q) return
  loading.value = true
  error.value = ''
  try {
    result.value = await searchHoldings(q, result.value.page, result.value.page_size)
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

function submit() {
  const q = keyword.value.trim()
  if (!q) return
  result.value.page = 1
  router.replace({ path: '/results', query: { q } })
  load()
}

function clearKeyword() {
  keyword.value = ''
}

function quickSearch(q) {
  keyword.value = q
  searchInput.value?.focus()
}

function goPage(p) {
  if (p < 1 || p > totalPages.value) return
  result.value.page = p
  load()
  router.replace({ path: '/results', query: { q: keyword.value.trim(), page: p } })
}

watch(
  () => result.value,
  () => {
    totalPages.value = Math.max(1, Math.ceil(result.value.total / result.value.page_size))
  },
  { deep: true }
)

watch(
  () => route.query.q,
  (q) => {
    if (q && q !== keyword.value.trim()) {
      keyword.value = q
      result.value.page = 1
      load()
    }
  }
)

onMounted(load)
</script>

<template>
  <div>
    <h1 class="sr-only">股东持股查询结果</h1>
    <section class="search-card">
      <label class="search-label" for="results-search">搜索股东</label>
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
            id="results-search"
            ref="searchInput"
            v-model="keyword"
            class="search-input has-clear"
            type="text"
            placeholder="输入股东姓名或 A 股代码…"
          />
          <button v-if="keyword" type="button" class="search-clear" @click="clearKeyword">
            清除
          </button>
        </div>
        <button type="submit" class="btn" :disabled="loading">查询</button>
      </form>
    </section>

    <QuickShareholders @select="quickSearch" />

    <p v-if="error" class="error">{{ error }}</p>
    <p v-else-if="loading" class="loading">加载中…</p>

    <template v-else-if="result.total > 0">
      <div class="results-summary">
        <span>
          共 <strong>{{ result.total }}</strong> 条持股记录，按披露时间从新到旧排序
        </span>
      </div>

      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>A股代码</th>
              <th>股票名称</th>
              <th>股东名称</th>
              <th>本期持股</th>
              <th>时间</th>
              <th>较上期变动</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="item in result.items"
              :key="`${item.stock_code}-${item.holder_name}-${item.end_date}`"
            >
              <td class="tabular-nums">{{ item.stock_code }}</td>
              <td>{{ item.stock_name }}</td>
              <td>{{ item.holder_name }}</td>
              <td class="tabular-nums">{{ fmt(item.hold_num) }}</td>
              <td class="tabular-nums">{{ item.end_date }}</td>
              <td>
                <span class="badge" :class="changeLabel(item).cls">
                  {{ changeLabel(item).text }}
                </span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <div class="pagination">
        <button class="page-btn" :disabled="result.page <= 1" @click="goPage(result.page - 1)">
          上一页
        </button>
        <span>{{ result.page }} / {{ totalPages }}</span>
        <button class="page-btn" :disabled="result.page >= totalPages" @click="goPage(result.page + 1)">
          下一页
        </button>
      </div>
    </template>

    <section v-else class="empty-state">
      <div class="empty-icon">🔍</div>
      <p>未找到相关持股记录，请换个股东姓名或 A 股代码试试。</p>
    </section>
  </div>
</template>
