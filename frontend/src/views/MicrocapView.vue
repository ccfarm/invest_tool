<script setup>
import { ref, computed, onMounted } from 'vue'
import {
  getLatestMicrocap,
  getMicrocapDates,
  getMicrocapHistory,
} from '../api'

const dates = ref([])
const selectedDate = ref('')
const snapshot = ref({ trade_date: null, created_at: null, items: [] })
const loading = ref(false)
const error = ref('')

const avgMktcap = computed(() => {
  const items = snapshot.value.items
  if (items.length === 0) return null
  const avg = items.reduce((sum, it) => sum + (it.mktcap_yi || 0), 0) / items.length
  return Math.round(avg * 100) / 100
})

async function loadDates() {
  try {
    const r = await getMicrocapDates()
    dates.value = r.dates || []
    if (!selectedDate.value && dates.value.length > 0) {
      selectedDate.value = dates.value[0].trade_date
    }
  } catch (e) {
    error.value = e.message
  }
}

async function loadSnapshot(date) {
  loading.value = true
  error.value = ''
  try {
    snapshot.value = date
      ? await getMicrocapHistory(date)
      : await getLatestMicrocap()
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

function onDateChange() {
  loadSnapshot(selectedDate.value)
}

function fmtCap(v) {
  return v == null ? '—' : `${v.toLocaleString('en-US')} 亿`
}

onMounted(async () => {
  await loadDates()
  await loadSnapshot(selectedDate.value || null)
})
</script>

<template>
  <div>
    <h1 class="sr-only">微盘股筛选</h1>

    <section class="search-card">
      <div class="microcap-toolbar">
        <label class="history-label" for="microcap-date">
          历史结果
          <select id="microcap-date" v-model="selectedDate" :disabled="dates.length === 0" @change="onDateChange">
            <option v-for="d in dates" :key="d.trade_date" :value="d.trade_date">
              {{ d.trade_date }}
            </option>
          </select>
        </label>
      </div>
      <p v-if="error" class="error">{{ error }}</p>
      <p class="microcap-note">
        数据每 6 小时自动更新，并自动补齐近 10 个交易日缺失的数据。
      </p>
    </section>

    <p v-if="loading" class="loading">加载中…</p>

    <template v-else-if="snapshot.items.length > 0">
      <div class="results-summary">
        <span>
          <strong>{{ snapshot.trade_date }}</strong> 交易日落选的微盘股（总市值最低 20 只）
        </span>
        <span v-if="avgMktcap != null">
          平均总市值 <strong>{{ fmtCap(avgMktcap) }}</strong>
        </span>
      </div>
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>排名</th>
              <th>代码</th>
              <th>名称</th>
              <th>总市值</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="item in snapshot.items" :key="item.code">
              <td class="tabular-nums">{{ item.rank }}</td>
              <td class="tabular-nums">{{ item.code }}</td>
              <td>{{ item.name }}</td>
              <td class="tabular-nums">{{ fmtCap(item.mktcap_yi) }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </template>

    <section v-else-if="!loading && !error" class="empty-state">
      <div class="empty-icon">📉</div>
      <p>还没有微盘股数据，服务每 6 小时自动拉取，请稍后再来查看。</p>
    </section>
  </div>
</template>
