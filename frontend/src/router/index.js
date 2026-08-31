import { createRouter, createWebHistory } from 'vue-router'
import HomeView from '../views/HomeView.vue'
import ResultsView from '../views/ResultsView.vue'
import MicrocapView from '../views/MicrocapView.vue'
import TrendView from '../views/TrendView.vue'
import LoginView from '../views/LoginView.vue'

const SITE_URL = 'http://www.cats789.fun'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'home', component: HomeView },
    { path: '/results', name: 'results', component: ResultsView },
    { path: '/microcap', name: 'microcap', component: MicrocapView },
    { path: '/trend', name: 'trend', component: TrendView },
    { path: '/login', name: 'login', component: LoginView },
  ],
})

const META = {
  home: {
    title: '股东查询 - A股十大股东持股记录与变动 | 投资工具箱',
    description:
      '输入股东姓名或 A 股代码，免费查询 A 股十大股东持股记录与持仓变动，覆盖沪深北全市场，数据每日更新。',
  },
  results: {
    title: '股东持股查询 - 查询结果 | 投资工具箱',
    description:
      '查看股东姓名或 A 股代码对应的持股记录与持仓变动，覆盖沪深北全市场，数据每日更新。',
  },
  microcap: {
    title: '微盘股筛选 - 总市值最低 30 只 A 股 | 投资工具箱',
    description:
      '查看最近交易日总市值最低的 30 只 A 股微盘股名单，排除 ST 及有 ST 风险的股票，数据每 6 小时更新。',
  },
  trend: {
    title: '趋势向上 - MA20 连续上行换手率最低 30 只 | 投资工具箱',
    description:
      '查看最近交易日 MA20 连续 10 个交易日上行、换手率最低的 30 只 A 股，悬停代码可查看近 3 个月日 K 线。',
  },
  login: {
    title: '登录 - 投资工具箱',
    description: '登录投资工具箱。',
  },
}

function setMeta(nameOrProperty, content) {
  const el =
    document.querySelector(`meta[name="${nameOrProperty}"]`) ||
    document.querySelector(`meta[property="${nameOrProperty}"]`)
  if (el) el.setAttribute('content', content)
}

function setCanonical(href) {
  let link = document.querySelector('link[rel="canonical"]')
  if (!link) {
    link = document.createElement('link')
    link.rel = 'canonical'
    document.head.appendChild(link)
  }
  link.href = href
}

router.afterEach((to) => {
  const base = META[to.name] || META.home
  const q = typeof to.query.q === 'string' && to.query.q.trim() ? to.query.q.trim() : ''
  const title = q && to.name === 'results' ? `「${q}」股东持股查询 - 投资工具箱` : base.title
  const description =
    q && to.name === 'results'
      ? `查询「${q}」的 A 股持股记录与持仓变动，覆盖沪深北全市场，数据每日更新。`
      : base.description
  const url = `${SITE_URL}${to.path}` + (q ? `?q=${encodeURIComponent(q)}` : '')

  document.title = title
  setMeta('description', description)
  setMeta('og:title', title)
  setMeta('og:description', description)
  setMeta('og:url', url)
  setMeta('twitter:title', title)
  setMeta('twitter:description', description)
  setCanonical(url)
})

export default router
