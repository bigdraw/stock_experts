import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '../stores/auth'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/login',
      name: 'Login',
      component: () => import('../views/Login.vue'),
    },
    {
      path: '/',
      component: () => import('../components/layout/AppLayout.vue'),
      meta: { requiresAuth: true },
      children: [
        { path: '', name: 'Dashboard', component: () => import('../views/Dashboard.vue') },
        { path: 'stocks', name: 'StockList', component: () => import('../views/StockList.vue') },
        { path: 'stocks/:code', name: 'StockDetail', component: () => import('../views/StockDetail.vue') },
        { path: 'portfolios', name: 'PortfolioList', component: () => import('../views/PortfolioList.vue') },
        { path: 'portfolios/:id', name: 'PortfolioDetail', component: () => import('../views/PortfolioDetail.vue') },
        { path: 'filters', name: 'FilterLibrary', component: () => import('../views/FilterLibrary.vue') },
        { path: 'backtest', name: 'BacktestCreate', component: () => import('../views/BacktestCreate.vue') },
        { path: 'backtest/results/:id', name: 'BacktestResult', component: () => import('../views/BacktestResult.vue') },
        { path: 'debate', name: 'DebateCreate', component: () => import('../views/DebateCreate.vue') },
        { path: 'books', name: 'BookManager', component: () => import('../views/BookManager.vue') },
        { path: 'alerts', name: 'AlertManager', component: () => import('../views/AlertManager.vue') },
        { path: 'settings', name: 'Settings', component: () => import('../views/Settings.vue') },
      ],
    },
  ],
})

router.beforeEach((to) => {
  const authStore = useAuthStore()
  if (to.meta.requiresAuth && !authStore.isLoggedIn) {
    return { name: 'Login' }
  }
})

export default router
