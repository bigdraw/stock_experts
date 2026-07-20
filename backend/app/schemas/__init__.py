"""Pydantic schemas for API request/response validation."""

from datetime import datetime

from pydantic import BaseModel, Field


# --- Auth ---
class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, description="用户名不能为空")
    password: str = Field(..., min_length=1, description="密码不能为空")


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    id: int
    username: str
    email: str | None = None
    role: str
    created_at: datetime

    class Config:
        from_attributes = True


class RegisterRequest(BaseModel):
    email: str = Field(..., description="邮箱（作为登录ID）")
    username: str = Field(..., min_length=1, max_length=50, description="显示用户名")
    password: str = Field(..., min_length=8, description="密码长度至少8位")


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


class StockWithIndicatorsResponse(BaseModel):
    code: str
    name: str
    market: str
    industry: str | None = None
    sector: str | None = None
    is_active: bool = True
    pe_ratio: float | None = None
    pb_ratio: float | None = None
    market_cap: float | None = None
    is_profitable: bool | None = None

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
    name: str = Field(..., min_length=1, max_length=100, description="组合名称不能为空")
    description: str | None = Field(None, max_length=500)


class PortfolioResponse(BaseModel):
    id: int
    name: str
    description: str | None = None
    created_at: datetime

    class Config:
        from_attributes = True


class PortfolioItemAddRequest(BaseModel):
    stock_code: str = Field(..., min_length=1, description="股票代码不能为空")
    shares: float = Field(0, ge=0, description="数量不能为负")
    avg_cost: float = Field(0, ge=0, description="成本不能为负")


# --- Agent ---
class AgentCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100, description="Agent名称不能为空")
    description: str | None = Field(None, max_length=500)
    nl_description: str = Field(..., min_length=1, description="描述不能为空")


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
    name: str = Field(..., min_length=1, max_length=200, description="筛选名称不能为空")
    nl_description: str = Field(..., min_length=1, description="描述不能为空")


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
    name: str = Field(..., min_length=1, max_length=200, description="策略名称不能为空")
    nl_description: str = Field(..., min_length=1, description="描述不能为空")


class BacktestRunRequest(BaseModel):
    strategy_id: int = Field(..., gt=0, description="策略ID必须大于0")
    stock_codes: list[str] | None = None
    start_date: str = Field(..., min_length=1, description="开始日期不能为空")
    end_date: str = Field(..., min_length=1, description="结束日期不能为空")
    initial_capital: float = Field(1_000_000, gt=0, description="初始资金必须大于0")
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
    agent_ids: list[int] = Field(..., min_length=2, description="至少需要2个Agent")
    target_type: str = Field(..., min_length=1, description="目标类型不能为空")
    target_id: str = Field(..., min_length=1, description="目标ID不能为空")
    rounds: int = Field(3, gt=0, le=10, description="轮数必须在1-10之间")


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
    name: str = Field(..., min_length=1, max_length=200, description="告警名称不能为空")
    nl_condition: str = Field(..., min_length=1, description="条件描述不能为空")
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
