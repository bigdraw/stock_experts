import { defineStore } from 'pinia'
import { ref } from 'vue'
import { notificationsApi } from '../api'
import type { Notification } from '../types'

export const useNotificationStore = defineStore('notifications', () => {
  const notifications = ref<Notification[]>([])
  const unreadCount = ref(0)

  async function fetchNotifications() {
    const res = await notificationsApi.list()
    notifications.value = res.data
  }

  async function fetchUnreadCount() {
    const res = await notificationsApi.unreadCount()
    unreadCount.value = res.data.count
  }

  async function markRead(id: number) {
    await notificationsApi.markRead(id)
    const n = notifications.value.find(n => n.id === id)
    if (n) n.is_read = true
    unreadCount.value = Math.max(0, unreadCount.value - 1)
  }

  async function markAllRead() {
    await notificationsApi.markAllRead()
    notifications.value.forEach(n => n.is_read = true)
    unreadCount.value = 0
  }

  return { notifications, unreadCount, fetchNotifications, fetchUnreadCount, markRead, markAllRead }
})
