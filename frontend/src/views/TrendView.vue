<script setup>
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import {
  getLatestTrend,
  getTrendDates,
  getTrendHistory,
  refreshTrend,
  getTrendKline,
} from '../api'

const dates = ref([])
const selectedDate = ref('')
const snapshot = ref({ trade_date: null, created_at: null, items: [] })
const loading = ref(false)
const refreshing = ref(false)
const error = ref('')

// 悬停 K 线
const tooltip = ref({ visible: false, x: 0, y: 0 })
const hoverCode = ref('')
const kline = ref({ code: '', name: '', loading: false, error: '', bars: [] })
const klineCache = new Map()

const CHART_W = 380
const CHART_H = 190
const CHART_PAD = 8
const TOOLTIP_W = 400

async function loadDates() {
  try {
    const r = await getTrendDates()
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
  hideTooltip()
  try {
    snapshot.value = date
      ? await getTrendHistory(date)
      : await getLatestTrend()
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

function onDateChange() {
  loadSnapshot(selectedDate.value)
}

async function handleRefresh() {
  refreshing.value = true
  error.value = ''
  try {
    const r = await refreshTrend()
    await loadDates()
    selectedDate.value = r.trade_date
    await loadSnapshot(r.trade_date)
  } catch (e) {
    error.value = e.message
  } finally {
    refreshing.value = false
  }
}

function fmtPrice(v) {
  return v == null ? '—' : Number(v).toFixed(2)
}

function fmtTurnover(v) {
  return v == null ? '—' : `${Number(v).toFixed(2)}%`
}

// ---------- 悬停 K 线 ----------
function hideTooltip() {
  tooltip.value.visible = false
  hoverCode.value = ''
}

function onCodeEnter(item, event) {
  hoverCode.value = item.code
  showKline(item)
  onCodeMove(event)
}

function onCodeMove(event) {
  if (!tooltip.value.visible) return
  const x = Math.min(event.clientX + 14, window.innerWidth - TOOLTIP_W - 8)
  const y = Math.min(event.clientY + 14, window.innerHeight - CHART_H - 72)
  tooltip.value = { visible: true, x: Math.max(8, x), y: Math.max(8, y) }
}

function onCodeLeave() {
  hideTooltip()
}

async function showKline(item) {
  const cached = klineCache.get(item.code)
  if (cached) {
    kline.value = { ...cached, name: item.name }
    tooltip.value.visible = true
    return
  }
  kline.value = { code: item.code, name: item.name, loading: true, error: '', bars: [] }
  tooltip.value.visible = true
  try {
    const r = await getTrendKline(item.code)
    const data = { code: item.code, name: item.name, loading: false, error: '', bars: r.bars || [] }
    klineCache.set(item.code, data)
    if (hoverCode.value === item.code) kline.value = data
  } catch {
    if (hoverCode.value === item.code) {
      kline.value = { code: item.code, name: item.name, loading: false, error: 'K线加载失败，请稍后再试', bars: [] }
    }
  }
}

const klineChart = computed(() => {
  const bars = kline.value.bars
  if (!bars || bars.length < 2) {
    return { width: CHART_W, height: CHART_H, candles: [], line: '', last: null }
  }
  const innerW = CHART_W - CHART_PAD * 2
  const innerH = CHART_H - CHART_PAD * 2
  const step = innerW / bars.length
  const bodyW = Math.max(2, Math.min(7, step * 0.62))
  const highs = bars.map((b) => b.high)
  const lows = bars.map((b) => b.low)
  const mas = bars.map((b) => b.ma20).filter((v) => v != null)
  let min = Math.min(...lows)
  let max = Math.max(...highs)
  if (mas.length > 0) {
    min = Math.min(min, ...mas)
    max = Math.max(max, ...mas)
  }
  const span = max - min || 1
  const y = (v) => CHART_PAD + ((max - v) / span) * innerH
  const x = (i) => CHART_PAD + i * step + step / 2
  const candles = bars.map((b, i) => {
    const up = b.close >= b.open
    const yOpen = y(b.open)
    const yClose = y(b.close)
    return {
      date: b.date,
      x: x(i),
      yOpen,
      yClose,
      yHigh: y(b.high),
      yLow: y(b.low),
      bodyH: Math.max(1, Math.abs(yOpen - yClose)),
      bodyW,
      up,
    }
  })
  const points = bars
    .map((b, i) => (b.ma20 == null ? null : `${x(i).toFixed(1)},${y(b.ma20).toFixed(1)}`))
    .filter(Boolean)
    .join(' ')
  return { width: CHART_W, height: CHART_H, candles, line: points, last: bars[bars.length - 1] }
})

onMounted(async () => {
  await loadDates()
  await loadSnapshot(selectedDate.value || null)
})

onBeforeUnmount(() => {
  hideTooltip()
})
</script>

<template>
  <div>
    <h1 class="sr-only">趋势向上</h1>

    <section class="search-card">
      <div class="microcap-toolbar">
        <label class="history-label" for="trend-date">
          历史结果
          <select id="trend-date" v-model="selectedDate" :disabled="dates.length === 0" @change="onDateChange">
            <option v-for="d in dates" :key="d.trade_date" :value="d.trade_date">
              {{ d.trade_date }}
            </option>
          </select>
        </label>
        <button type="button" class="btn" :disabled="refreshing" @click="handleRefresh">
          {{ refreshing ? '筛选中…' : '刷新' }}
        </button>
      </div>
      <p v-if="error" class="error">{{ error }}</p>
      <p class="microcap-note">
        MA20 连续 10 个交易日上行 · 按换手率从小到大取 30 只 · 悬停代码查看近 3 个月 K 线
      </p>
    </section>

    <p v-if="loading" class="loading">加载中…</p>

    <template v-else-if="snapshot.items.length > 0">
      <div class="results-summary">
        <span>
          <strong>{{ snapshot.trade_date }}</strong> 日入选（MA20 连续 10 个交易日上行，换手率最低 30 只）
        </span>
      </div>
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>排名</th>
              <th>代码</th>
              <th>名称</th>
              <th>现价</th>
              <th>换手率</th>
              <th>MA20</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="item in snapshot.items" :key="item.code">
              <td class="tabular-nums">{{ item.rank }}</td>
              <td>
                <router-link
                  class="code-link"
                  :to="{ path: '/results', query: { q: item.code } }"
                  @mouseenter="onCodeEnter(item, $event)"
                  @mousemove="onCodeMove"
                  @mouseleave="onCodeLeave"
                >
                  {{ item.code }}
                </router-link>
              </td>
              <td>{{ item.name }}</td>
              <td class="tabular-nums">{{ fmtPrice(item.price) }}</td>
              <td class="tabular-nums">{{ fmtTurnover(item.turnover) }}</td>
              <td class="tabular-nums">{{ fmtPrice(item.ma20) }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </template>

    <section v-else-if="!loading && !error" class="empty-state">
      <div class="empty-icon">📈</div>
      <p>还没有趋势数据，服务每 6 小时自动拉取，请稍后再来查看。</p>
    </section>

    <!-- 悬停 K 线提示 -->
    <div v-if="tooltip.visible" class="kline-tip" :style="{ left: tooltip.x + 'px', top: tooltip.y + 'px' }">
      <div class="kline-tip-head">
        <strong>{{ kline.code }}</strong>
        <span>{{ kline.name }}</span>
        <span v-if="klineChart.last" class="kline-tip-date">{{ klineChart.last.date }}</span>
      </div>
      <div v-if="kline.loading" class="kline-tip-loading">K线加载中…</div>
      <p v-else-if="kline.error" class="kline-tip-error">{{ kline.error }}</p>
      <svg
        v-else-if="kline.bars.length > 0"
        :width="klineChart.width"
        :height="klineChart.height"
        class="kline-chart"
        aria-hidden="true"
      >
        <g v-for="c in klineChart.candles" :key="c.date">
          <line
            :x1="c.x"
            :x2="c.x"
            :y1="c.yHigh"
            :y2="c.yLow"
            :stroke="c.up ? 'var(--state-error)' : 'var(--state-success)'"
            stroke-width="1"
          />
          <rect
            :x="c.x - c.bodyW / 2"
            :y="c.up ? c.yClose : c.yOpen"
            :width="c.bodyW"
            :height="c.bodyH"
            :fill="c.up ? 'var(--state-error)' : 'var(--state-success)'"
          />
        </g>
        <polyline
          v-if="klineChart.line"
          :points="klineChart.line"
          fill="none"
          stroke="var(--brand-500)"
          stroke-width="1.2"
        />
      </svg>
      <p v-else class="kline-tip-error">暂无K线数据</p>
      <p v-if="kline.bars.length > 0" class="kline-legend">红涨绿跌 · 紫色为 MA20 · 悬停查看 3 个月日 K</p>
    </div>
  </div>
</template>
