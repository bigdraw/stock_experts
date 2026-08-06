import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { authApi } from '../api'
import type { User } from '../types'

export const useAuthStore = defineStore('auth', () => {
  // sessionStorage (not localStorage) so the token dies with the tab instead
  // of persisting across restarts/browsing history (ISSUE-026). DOMPurify in
  // MarkdownRenderer closes the XSS-to-token-theft chain; sessionStorage is
  // defense-in-depth. Full fix = httpOnly cookie + CSRF (tracked in ISSUES).
  const token = ref<string | null>(sessionStorage.getItem('token'))
  const user = ref<User | null>(null)
  const isLoggedIn = computed(() => !!token.value)

  async function login(username: string, password: string) {
    const res = await authApi.login(username, password)
    token.value = res.data.access_token
    sessionStorage.setItem('token', res.data.access_token)
    await fetchUser()
  }

  async function register(username: string, password: string) {
    await authApi.register(username, password)
    await login(username, password)
  }

  async function fetchUser() {
    try {
      const res = await authApi.getMe()
      user.value = res.data
    } catch {
      logout()
    }
  }

  function logout() {
    token.value = null
    user.value = null
    sessionStorage.removeItem('token')
  }

  return { token, user, isLoggedIn, login, register, fetchUser, logout }
})
