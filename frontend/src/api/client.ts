import axios from 'axios'
import { useAuthStore } from '../stores/auth'
import router from '../router'

const apiClient = axios.create({
  baseURL: '/api/v1',
  headers: { 'Content-Type': 'application/json' },
  timeout: 30000,
})

// Admin client uses root path (no /api/v1 prefix)
const adminClient = axios.create({
  baseURL: '',
  headers: { 'Content-Type': 'application/json' },
  timeout: 30000,
})

function addAuthInterceptor(client: ReturnType<typeof axios.create>) {
  client.interceptors.request.use((config) => {
    const authStore = useAuthStore()
    if (authStore.token) {
      config.headers.Authorization = `Bearer ${authStore.token}`
    }
    return config
  })

  client.interceptors.response.use(
    (response) => response,
    (error) => {
      if (error.response?.status === 401) {
        // Guard against N concurrent 401s all calling logout/push at once
        // (ISSUE-027): only the first one (when a token still exists) acts.
        const authStore = useAuthStore()
        if (authStore.token) {
          authStore.logout()
          router.push('/login')
        }
      }
      return Promise.reject(error)
    }
  )
}

addAuthInterceptor(apiClient)
addAuthInterceptor(adminClient)

/**
 * Handle auth failure on a streaming (fetch) path that bypasses the axios
 * interceptor (ISSUE-027). SSE streams use raw fetch; a 401 there previously
 * only surfaced as a ⚠️ HTTP 401 bubble, leaving the user on a stale
 * "logged-in" UI. Call this in the `!res.ok` branch of every stream fetch.
 */
export function handleStreamAuthFailure(status: number): void {
  if (status === 401) {
    const authStore = useAuthStore()
    if (authStore.token) {
      authStore.logout()
      router.push('/login')
    }
  }
}

export { adminClient }
export default apiClient
