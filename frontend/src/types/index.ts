export interface User {
  id: number
  username: string
  role: string
  created_at: string
}

export interface Stock {
  code: string
  name: string
  market: string
  industry?: string
  sector?: string
  is_active: boolean
}

export interface DailyQuote {
  date: string
  open?: number
  high?: number
  low?: number
  close?: number
  volume?: number
  amount?: number
  turnover_rate?: number
}

export interface Portfolio {
  id: number
  name: string
  description?: string
  created_at: string
}

export interface PortfolioDetail extends Portfolio {
  holdings: PortfolioHolding[]
}

export interface PortfolioHolding {
  id: number
  stock_code: string
  stock_name: string
  shares: number
  avg_cost: number
  added_at: string
}

export interface Agent {
  id: number
  name: string
  type: string
  description?: string
  is_active: boolean
  created_at: string
}

export interface FilterScript {
  id: number
  name: string
  nl_description: string
  is_verified: boolean
  usage_count: number
  created_at: string
}

export interface BacktestStrategy {
  id: number
  name: string
  nl_description: string
  code?: string
  created_at: string
}

export interface BacktestResult {
  id: number
  strategy_id: number
  total_return?: number
  annualized_return?: number
  max_drawdown?: number
  sharpe_ratio?: number
  win_rate?: number
  total_trades?: number
  final_capital?: number
  equity_curve?: Array<{ date: string; value: number }>
  trade_log?: Array<Record<string, unknown>>
  created_at: string
}

export interface Notification {
  id: number
  type: string
  title: string
  content?: string
  is_read: boolean
  created_at: string
}

export interface Alert {
  id: number
  name: string
  nl_condition: string
  target_type?: string
  is_active: boolean
  last_triggered_at?: string
  created_at: string
}

export interface DebateRound {
  round_type: string
  opinions: Array<{ agent_name: string; content: string }>
}

export interface DebateResult {
  rounds: DebateRound[]
  summary: string
}

export interface AdminUser {
  id: number
  username: string
  role: string
  is_active: boolean
  created_at: string
  updated_at: string
}
