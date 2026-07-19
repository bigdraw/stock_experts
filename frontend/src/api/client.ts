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
        const authStore = useAuthStore()
        authStore.logout()
        router.push('/login')
      }
      return Promise.reject(error)
    }
  )
}

addAuthInterceptor(apiClient)
addAuthInterceptor(adminClient)

export { adminClient }
export default apiClient
