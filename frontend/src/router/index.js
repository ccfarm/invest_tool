import { createRouter, createWebHistory } from 'vue-router'
import HomeView from '../views/HomeView.vue'
import ResultsView from '../views/ResultsView.vue'
import MicrocapView from '../views/MicrocapView.vue'
import LoginView from '../views/LoginView.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'home', component: HomeView },
    { path: '/results', name: 'results', component: ResultsView },
    { path: '/microcap', name: 'microcap', component: MicrocapView },
    { path: '/login', name: 'login', component: LoginView },
  ],
})

const TITLES = {
  home: '股东查询 - A股股东持股记录与变动',
  results: '查询结果 - 股东查询',
  microcap: '微盘股筛选 - 投资工具箱',
  login: '登录 - 投资工具箱',
}

router.afterEach((to) => {
  document.title = TITLES[to.name] || TITLES.home
})

export default router
