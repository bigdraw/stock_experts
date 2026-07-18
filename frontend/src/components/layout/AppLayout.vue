<template>
  <n-layout has-sider style="height: 100vh">
    <n-layout-sider bordered collapse-mode="width" :collapsed-width="64" :width="220" show-trigger>
      <div style="padding: 16px; text-align: center; font-weight: bold; font-size: 18px">
        股票分析平台
      </div>
      <n-menu :options="menuOptions" :value="activeKey" @update:value="handleMenuClick" />
    </n-layout-sider>
    <n-layout>
      <n-layout-header bordered style="padding: 12px 24px; display: flex; justify-content: space-between; align-items: center">
        <n-breadcrumb>
          <n-breadcrumb-item>{{ currentRoute }}</n-breadcrumb-item>
        </n-breadcrumb>
        <n-space>
          <n-badge :value="notificationStore.unreadCount" :max="99">
            <n-button quaternary @click="$router.push('/notifications')">
              <template #icon><n-icon><NotificationsOutline /></n-icon></template>
            </n-button>
          </n-badge>
          <n-dropdown :options="userMenuOptions" @select="handleUserMenu">
            <n-button quaternary>{{ authStore.user?.username || 'User' }}</n-button>
          </n-dropdown>
        </n-space>
      </n-layout-header>
      <n-layout-content content-style="padding: 24px;">
        <router-view />
      </n-layout-content>
    </n-layout>
  </n-layout>
</template>

<script setup lang="ts">
import { computed, h, onMounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { NIcon } from 'naive-ui'
import {
  HomeOutline, TrendingUpOutline, BriefcaseOutline, FunnelOutline,
  BarChartOutline, ChatbubblesOutline, BookOutline, NotificationsOutline,
  SettingsOutline, LogOutOutline,
} from '@vicons/ionicons5'
import { useAuthStore } from '../../stores/auth'
import { useNotificationStore } from '../../stores/notifications'

const router = useRouter()
const route = useRoute()
const authStore = useAuthStore()
const notificationStore = useNotificationStore()

const activeKey = computed(() => route.name as string)
const currentRoute = computed(() => route.name as string)

function renderIcon(icon: any) {
  return () => h(NIcon, null, { default: () => h(icon) })
}

const menuOptions = [
  { label: '仪表盘', key: 'Dashboard', icon: renderIcon(HomeOutline) },
  { label: '股票列表', key: 'StockList', icon: renderIcon(TrendingUpOutline) },
  { label: '投资组合', key: 'PortfolioList', icon: renderIcon(BriefcaseOutline) },
  { label: '筛选工具库', key: 'FilterLibrary', icon: renderIcon(FunnelOutline) },
  { label: '策略回测', key: 'BacktestCreate', icon: renderIcon(BarChartOutline) },
  { label: '辩论分析', key: 'DebateCreate', icon: renderIcon(ChatbubblesOutline) },
  { label: '书籍管理', key: 'BookManager', icon: renderIcon(BookOutline) },
  { label: '告警管理', key: 'AlertManager', icon: renderIcon(NotificationsOutline) },
  { label: '系统设置', key: 'Settings', icon: renderIcon(SettingsOutline) },
]

const userMenuOptions = [
  { label: '退出登录', key: 'logout', icon: renderIcon(LogOutOutline) },
]

function handleMenuClick(key: string) {
  router.push({ name: key })
}

function handleUserMenu(key: string) {
  if (key === 'logout') {
    authStore.logout()
    router.push('/login')
  }
}

onMounted(async () => {
  if (authStore.isLoggedIn) {
    await authStore.fetchUser()
    await notificationStore.fetchUnreadCount()
  }
})
</script>
