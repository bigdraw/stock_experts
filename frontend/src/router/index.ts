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
        { path: '', name: 'ChatHome', component: () => import('../views/ChatHome.vue') },
        { path: 'dashboard', name: 'Dashboard', component: () => import('../views/Dashboard.vue') },
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
        { 
          path: 'admin/users', 
          name: 'AdminUsers', 
          component: () => import('../views/AdminUsers.vue'),
          meta: { requiresAuth: true, requiresAdmin: true }
        },
      ],
    },
  ],
})

router.beforeEach(async (to) => {
  const authStore = useAuthStore()

  // Check if route requires authentication
  if (to.meta.requiresAuth && !authStore.isLoggedIn) {
    return { name: 'Login' }
  }

  // Check if route requires admin role.
  // authStore.user may be null on a fresh page load (token present in
  // localStorage but /auth/me not yet called). Resolve it before deciding,
  // otherwise a direct-link to an admin route bounces to Dashboard even for
  // admins. fetchUser() is a no-op once user is populated.
  if (to.meta.requiresAdmin) {
    if (!authStore.user && authStore.isLoggedIn) {
      await authStore.fetchUser()
    }
    if (authStore.user?.role !== 'admin') {
      return { name: 'Dashboard' }
    }
  }
})

export default router
