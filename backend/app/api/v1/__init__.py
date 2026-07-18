"""API v1 router aggregation."""

from fastapi import APIRouter

from app.api.v1.auth import router as auth_router
from app.api.v1.stocks import router as stocks_router
from app.api.v1.filters import router as filters_router
from app.api.v1.data import router as data_router
from app.api.v1.books import router as books_router
from app.api.v1.portfolios import router as portfolios_router
from app.api.v1.backtest import router as backtest_router
from app.api.v1.debate import router as debate_router
from app.api.v1.notifications import router as notifications_router

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth_router)
api_router.include_router(stocks_router)
api_router.include_router(filters_router)
api_router.include_router(data_router)
api_router.include_router(books_router)
api_router.include_router(portfolios_router)
api_router.include_router(backtest_router)
api_router.include_router(debate_router)
api_router.include_router(notifications_router)
