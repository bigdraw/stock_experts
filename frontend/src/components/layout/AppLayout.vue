<template>
  <n-layout has-sider style="height: 100vh">
    <n-layout-sider
      bordered
      collapse-mode="width"
      :collapsed-width="64"
      :width="240"
      show-trigger
      :collapsed="collapsed"
      @collapse="collapsed = true"
      @expand="collapsed = false"
      :native-scrollbar="false"
      style="background: linear-gradient(180deg, rgba(15, 23, 42, 0.95) 0%, rgba(10, 14, 26, 0.95) 100%); backdrop-filter: blur(12px);"
    >
      <div class="logo-container">
        <div class="logo-glow"></div>
        <h1 class="logo-text">
          <span class="gradient-text">股票分析</span>
          <span class="logo-subtitle">智能投资平台</span>
        </h1>
      </div>
      <n-menu
        :collapsed="collapsed"
        :collapsed-width="64"
        :collapsed-icon-size="22"
        :options="menuOptions"
        :value="activeKey"
        @update:value="handleMenuClick"
      />
    </n-layout-sider>
    <n-layout>
      <n-layout-header 
        bordered 
        style="padding: 16px 32px; display: flex; justify-content: space-between; align-items: center; background: rgba(15, 23, 42, 0.6); backdrop-filter: blur(12px);"
      >
        <n-breadcrumb>
          <n-breadcrumb-item>
            <span style="font-weight: 600; color: var(--text-primary);">{{ currentRoute }}</span>
          </n-breadcrumb-item>
        </n-breadcrumb>
        <n-space :size="12">
          <n-badge :value="notificationStore.unreadCount" :max="99">
            <n-button quaternary circle @click="$router.push('/alerts')" style="transition: all 0.3s;">
              <template #icon>
                <n-icon :size="20"><NotificationsOutline /></n-icon>
              </template>
            </n-button>
          </n-badge>
          <!-- 语言切换 (idea17) -->
          <n-dropdown :options="langOptions" @select="(k: string) => setLocale(k as any)" trigger="click">
            <n-button quaternary size="small">
              <span style="font-size: 13px; font-weight: 500;">{{ locale === 'zh' ? '中' : locale === 'en' ? 'EN' : locale === 'ja' ? '日' : '한' }}</span>
            </n-button>
          </n-dropdown>
          <n-dropdown :options="userMenuOptions" @select="handleUserMenu">
            <n-button quaternary style="transition: all 0.3s;">
              <template #icon>
                <n-icon :size="20"><PersonCircleOutline /></n-icon>
              </template>
              <span style="font-weight: 500;">{{ authStore.user?.username || 'User' }}</span>
            </n-button>
          </n-dropdown>
        </n-space>
      </n-layout-header>
      <n-layout-content 
        content-style="padding: 32px;" 
        :native-scrollbar="false"
        style="background: var(--bg-base);"
      >
        <router-view v-slot="{ Component }">
          <transition name="fade-in" mode="out-in">
            <component :is="Component" />
          </transition>
        </router-view>
      </n-layout-content>
    </n-layout>
  </n-layout>
</template>

<script setup lang="ts">
import { computed, h, ref, onMounted, onUnmounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { NIcon } from 'naive-ui'
import {
  HomeOutline,
  TrendingUpOutline,
  BriefcaseOutline,
  FunnelOutline,
  BarChartOutline,
  ChatbubblesOutline,
  BookOutline,
  NotificationsOutline,
  SettingsOutline,
  LogOutOutline,
  PersonCircleOutline,
  ShieldCheckmarkOutline
} from '@vicons/ionicons5'
import { useAuthStore } from '../../stores/auth'
import { useNotificationStore } from '../../stores/notifications'
import { locale, setLocale } from '../../i18n'

const router = useRouter()
const route = useRoute()
const authStore = useAuthStore()
const notificationStore = useNotificationStore()
const collapsed = ref(false)
let notifTimer: ReturnType<typeof setInterval> | null = null

const langOptions = [
  { label: '中文', key: 'zh' },
  { label: 'English', key: 'en' },
  { label: '日本語', key: 'ja' },
  { label: '한국어', key: 'ko' },
]

const activeKey = computed(() => route.name as string)
const currentRoute = computed(() => route.name as string)

function renderIcon(icon: any) {
  return () => h(NIcon, null, { default: () => h(icon) })
}

const menuOptions = computed(() => {
  const baseMenu = [
    { label: '对话', key: 'ChatHome', icon: renderIcon(ChatbubblesOutline) },
    { label: '仪表盘', key: 'Dashboard', icon: renderIcon(HomeOutline) },
    { label: '股票列表', key: 'StockList', icon: renderIcon(TrendingUpOutline) },
    { label: '投资组合', key: 'PortfolioList', icon: renderIcon(BriefcaseOutline) },
    { label: '筛选工具库', key: 'FilterLibrary', icon: renderIcon(FunnelOutline) },
    { label: '策略回测', key: 'BacktestCreate', icon: renderIcon(BarChartOutline) },
    { label: '辩论分析', key: 'DebateCreate', icon: renderIcon(ChatbubblesOutline) },
    { label: 'Agent构建', key: 'BookManager', icon: renderIcon(BookOutline) },
    { label: '告警管理', key: 'AlertManager', icon: renderIcon(NotificationsOutline) },
    { label: '系统设置', key: 'Settings', icon: renderIcon(SettingsOutline) },
  ]
  
  // Add admin menu if user is admin
  if (authStore.user?.role === 'admin') {
    baseMenu.push({
      label: '用户管理',
      key: 'AdminUsers',
      icon: renderIcon(ShieldCheckmarkOutline)
    })
  }
  
  return baseMenu
})

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
    // Periodically refresh the unread badge so the bell stays current.
    notifTimer = setInterval(() => {
      notificationStore.fetchUnreadCount().catch(() => {})
    }, 60000)
  }
})

onUnmounted(() => {
  if (notifTimer) {
    clearInterval(notifTimer)
    notifTimer = null
  }
})
</script>

<style scoped>
.logo-container {
  position: relative;
  padding: 28px 20px;
  text-align: center;
  border-bottom: 1px solid var(--border-subtle);
  overflow: hidden;
}

.logo-glow {
  position: absolute;
  top: -50%;
  left: 50%;
  transform: translateX(-50%);
  width: 200px;
  height: 200px;
  background: radial-gradient(circle, var(--primary-glow) 0%, transparent 70%);
  opacity: 0.6;
  pointer-events: none;
  animation: pulse 4s ease-in-out infinite;
}

@keyframes pulse {
  0%, 100% {
    opacity: 0.4;
    transform: translateX(-50%) scale(1);
  }
  50% {
    opacity: 0.7;
    transform: translateX(-50%) scale(1.1);
  }
}

.logo-text {
  position: relative;
  z-index: 1;
  margin: 0;
  font-size: 22px;
  font-weight: 700;
  line-height: 1.2;
  letter-spacing: -0.5px;
}

.logo-subtitle {
  display: block;
  font-size: 11px;
  font-weight: 500;
  color: var(--text-tertiary);
  margin-top: 6px;
  letter-spacing: 1px;
  text-transform: uppercase;
}
</style>
