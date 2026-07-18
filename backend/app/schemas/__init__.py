"""Pydantic schemas for API request/response validation."""

from datetime import datetime
from pydantic import BaseModel


# --- Auth ---
class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    id: int
    username: str
    role: str
    created_at: datetime

    class Config:
        from_attributes = True


class RegisterRequest(BaseModel):
    username: str
    password: str


# --- Stock ---
class StockResponse(BaseModel):
    code: str
    name: str
    market: str
    industry: str | None = None
    sector: str | None = None
    is_active: bool = True

    class Config:
        from_attributes = True


class DailyQuoteResponse(BaseModel):
    date: str
    open: float | None = None
    high: float | None = None
    low: float | None = None
    close: float | None = None
    volume: float | None = None
    amount: float | None = None
    turnover_rate: float | None = None

    class Config:
        from_attributes = True


# --- Portfolio ---
class PortfolioCreateRequest(BaseModel):
    name: str
    description: str | None = None


class PortfolioResponse(BaseModel):
    id: int
    name: str
    description: str | None = None
    created_at: datetime

    class Config:
        from_attributes = True


class PortfolioItemAddRequest(BaseModel):
    stock_code: str
    shares: float = 0
    avg_cost: float = 0


# --- Agent ---
class AgentCreateRequest(BaseModel):
    name: str
    description: str | None = None
    nl_description: str  # natural language description for manual agent


class AgentResponse(BaseModel):
    id: int
    name: str
    type: str
    description: str | None = None
    is_active: bool = True
    created_at: datetime

    class Config:
        from_attributes = True


# --- Filter ---
class FilterGenerateRequest(BaseModel):
    name: str
    nl_description: str


class FilterExecuteRequest(BaseModel):
    params: dict | None = None


class FilterResponse(BaseModel):
    id: int
    name: str
    nl_description: str
    is_verified: bool = False
    usage_count: int = 0
    created_at: datetime

    class Config:
        from_attributes = True


# --- Backtest ---
class BacktestGenerateRequest(BaseModel):
    name: str
    nl_description: str


class BacktestRunRequest(BaseModel):
    strategy_id: int
    stock_codes: list[str] | None = None
    start_date: str
    end_date: str
    initial_capital: float = 1_000_000
    friction_config: dict | None = None


class BacktestResultResponse(BaseModel):
    id: int
    strategy_id: int
    total_return: float | None = None
    annualized_return: float | None = None
    max_drawdown: float | None = None
    sharpe_ratio: float | None = None
    win_rate: float | None = None
    total_trades: int | None = None
    final_capital: float | None = None
    created_at: datetime

    class Config:
        from_attributes = True


# --- Debate ---
class DebateStartRequest(BaseModel):
    agent_ids: list[int]
    target_type: str  # stock / portfolio
    target_id: str
    rounds: int = 3


# --- Book ---
class BookUploadResponse(BaseModel):
    id: int
    filename: str
    status: str


# --- Notification ---
class NotificationResponse(BaseModel):
    id: int
    type: str
    title: str
    content: str | None = None
    is_read: bool = False
    created_at: datetime

    class Config:
        from_attributes = True


class AlertCreateRequest(BaseModel):
    name: str
    nl_condition: str
    target_type: str | None = None
    target_id: str | None = None


class AlertResponse(BaseModel):
    id: int
    name: str
    nl_condition: str
    target_type: str | None = None
    is_active: bool = True
    last_triggered_at: datetime | None = None
    created_at: datetime

    class Config:
        from_attributes = True
