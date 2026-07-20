import apiClient, { adminClient } from './client'
import type { Stock, DailyQuote, Portfolio, PortfolioDetail, Agent, FilterScript, BacktestStrategy, BacktestResult, Notification, Alert, DebateResult, AdminUser } from '../types'

// Auth
export const authApi = {
  login: (username: string, password: string) => apiClient.post('/auth/login', { username, password }),
  register: (username: string, password: string) => apiClient.post('/auth/register', { username, password }),
  getMe: () => apiClient.get('/auth/me'),
}

// Stocks
export const stocksApi = {
  list: (params?: { market?: string; search?: string; limit?: number; offset?: number }) =>
    apiClient.get<Stock[]>('/stocks', { params }),
  listWithIndicators: (params?: { market?: string; search?: string; limit?: number; offset?: number }) =>
    apiClient.get<any[]>('/stocks/with-indicators', { params }),
  count: (params?: { market?: string }) =>
    apiClient.get<{ count: number }>('/stocks/count', { params }),
  search: (q: string, limit: number = 100) =>
    apiClient.get<Stock[]>('/stocks/search', { params: { q, limit } }),
  get: (code: string) => apiClient.get<Stock>(`/stocks/${code}`),
  getQuotes: (code: string, opts: { period?: string; limit?: number; days?: number } = {}) =>
    apiClient.get<DailyQuote[]>(`/stocks/${code}/quotes`, {
      params: { period: opts.period ?? 'daily', limit: opts.limit ?? 1000, days: opts.days ?? 120 },
    }),
  getFinancials: (code: string) => apiClient.get(`/stocks/${code}/financials`),
  getIndicators: (code: string) => apiClient.get(`/stocks/${code}/indicators`),
}

// Portfolios
export const portfoliosApi = {
  list: () => apiClient.get<Portfolio[]>('/portfolios'),
  create: (name: string, description?: string) => apiClient.post<Portfolio>('/portfolios', { name, description }),
  get: (id: number) => apiClient.get<PortfolioDetail>(`/portfolios/${id}`),
  delete: (id: number) => apiClient.delete(`/portfolios/${id}`),
  addStock: (id: number, stockCode: string, shares: number = 0, avgCost: number = 0) =>
    apiClient.post(`/portfolios/${id}/items`, { stock_code: stockCode, shares, avg_cost: avgCost }),
  addByFilter: (id: number, filterId: number, params?: Record<string, unknown>) =>
    apiClient.post(`/portfolios/${id}/items/filter`, null, { params: { filter_id: filterId, ...params } }),
  removeStock: (id: number, stockCode: string) => apiClient.delete(`/portfolios/${id}/items/${stockCode}`),
  removeStockById: (portfolioId: number, itemId: number) => apiClient.delete(`/portfolios/${portfolioId}/items/by-id/${itemId}`),
}

// Filters
export const filtersApi = {
  list: () => apiClient.get<FilterScript[]>('/filters'),
  generate: (name: string, nlDescription: string) =>
    apiClient.post<FilterScript>('/filters/generate', { name, nl_description: nlDescription }),
  execute: (id: number, params?: Record<string, unknown>) =>
    apiClient.post(`/filters/${id}/execute`, { params }),
  delete: (id: number) => apiClient.delete(`/filters/${id}`),
}

// Agents
export const agentsApi = {
  list: () => apiClient.get<Agent[]>('/agents'),
  create: (name: string, nlDescription: string, description?: string) =>
    apiClient.post<Agent>('/agents', { name, nl_description: nlDescription, description }),
  get: (id: number) => apiClient.get<Agent>(`/agents/${id}`),
  delete: (id: number) => apiClient.delete(`/agents/${id}`),
}

// Backtest
export const backtestApi = {
  generate: (name: string, nlDescription: string) =>
    apiClient.post('/backtest/generate', { name, nl_description: nlDescription }),
  run: (strategyId: number, stockCodes: string[], startDate: string, endDate: string, initialCapital: number = 1000000) =>
    apiClient.post<BacktestResult>('/backtest/run', {
      strategy_id: strategyId, stock_codes: stockCodes, start_date: startDate, end_date: endDate, initial_capital: initialCapital,
    }),
  listStrategies: () => apiClient.get<BacktestStrategy[]>('/backtest/strategies'),
  listResults: () => apiClient.get<BacktestResult[]>('/backtest/results'),
}

// Debate
export const debateApi = {
  start: (agentIds: number[], targetType: string, targetId: string, rounds: number = 3) =>
    apiClient.post<DebateResult>('/debate/start', { agent_ids: agentIds, target_type: targetType, target_id: targetId, rounds }),
}

// Books
export const booksApi = {
  upload: (file: File) => {
    const formData = new FormData()
    formData.append('file', file)
    return apiClient.post('/books/upload', formData, { headers: { 'Content-Type': 'multipart/form-data' } })
  },
  generateAgent: (filePath: string) => apiClient.post('/books/generate-agent', null, { params: { file_path: filePath } }),
}

// Notifications
export const notificationsApi = {
  list: () => apiClient.get<Notification[]>('/notifications'),
  unreadCount: () => apiClient.get<{ count: number }>('/notifications/unread-count'),
  markRead: (id: number) => apiClient.put(`/notifications/${id}/read`),
  markAllRead: () => apiClient.put('/notifications/read-all'),
}

// Alerts
export const alertsApi = {
  list: () => apiClient.get<Alert[]>('/notifications/alerts'),
  create: (name: string, nlCondition: string, targetType?: string, targetId?: string) =>
    apiClient.post<Alert>('/notifications/alerts', { name, nl_condition: nlCondition, target_type: targetType, target_id: targetId }),
  toggle: (id: number) => apiClient.put(`/notifications/alerts/${id}/toggle`),
  delete: (id: number) => apiClient.delete(`/notifications/alerts/${id}`),
}

// Data
export const dataApi = {
  startFullCollection: () => apiClient.post('/data/collect/full'),
  startIncrementalUpdate: () => apiClient.post('/data/collect/incremental'),
  startDeepFetch: (stockCodes: string[]) => apiClient.post('/data/collect/deep', stockCodes),
  startFinancialUpdate: () => apiClient.post('/data/collect/financial'),
  getStatus: () => apiClient.get('/data/collect/status'),
}

// Tasks
export const tasksApi = {
  list: () => apiClient.get('/tasks'),
  get: (taskId: string) => apiClient.get(`/tasks/${taskId}`),
  pause: (taskId: string) => apiClient.post(`/tasks/${taskId}/pause`),
  resume: (taskId: string) => apiClient.post(`/tasks/${taskId}/resume`),
  stop: (taskId: string) => apiClient.post(`/tasks/${taskId}/stop`),
  delete: (taskId: string) => apiClient.delete(`/tasks/${taskId}`),
}

// Settings
export interface LLMConfig {
  provider: string
  base_url: string
  api_key: string
  model: string
  max_tokens: number
  temperature: number
}

export interface DataSourceConfig {
  provider: string
  rate_limit: number
  retry_max: number
}

export interface FrictionConfig {
  stamp_tax: number
  commission: number
  commission_min: number
  slippage: number
}

export const settingsApi = {
  // Proxy
  getProxy: () => apiClient.get<{ enabled: boolean }>('/settings/proxy'),
  setProxy: (enabled: boolean) => apiClient.put('/settings/proxy', { enabled }),
  testConnection: () => apiClient.post<{ success: boolean; message: string }>('/settings/test-connection'),

  // LLM
  getLLM: () => apiClient.get<LLMConfig>('/settings/llm'),
  setLLM: (config: LLMConfig) => apiClient.put<LLMConfig>('/settings/llm', config),
  testLLM: () => apiClient.post<{ success: boolean; message: string }>('/settings/test-llm'),

  // Data Source
  getDataSource: () => apiClient.get<DataSourceConfig>('/settings/data-source'),
  setDataSource: (config: DataSourceConfig) => apiClient.put<DataSourceConfig>('/settings/data-source', config),

  // Friction
  getFriction: () => apiClient.get<FrictionConfig>('/settings/friction'),
  setFriction: (config: FrictionConfig) => apiClient.put<FrictionConfig>('/settings/friction', config),
}

// Admin
export const adminApi = {
  listUsers: () => adminClient.get<AdminUser[]>('/admin/users'),
  resetPassword: (userId: number, newPassword: string) =>
    adminClient.post(`/admin/users/${userId}/reset-password`, { new_password: newPassword }),
  updateUserRole: (userId: number, role: string) =>
    adminClient.put(`/admin/users/${userId}/role`, { role }),
  updateUserStatus: (userId: number, isActive: boolean) =>
    adminClient.put(`/admin/users/${userId}/status`, { is_active: isActive }),
  deleteUser: (userId: number) => adminClient.delete(`/admin/users/${userId}`),
}
