"""API v1 router aggregation."""

from fastapi import APIRouter

from app.api.v1.auth import router as auth_router

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth_router)

# Additional routers will be added as modules are implemented:
# from app.api.v1.stocks import router as stocks_router
# from app.api.v1.portfolios import router as portfolios_router
# from app.api.v1.agents import router as agents_router
# from app.api.v1.filters import router as filters_router
# from app.api.v1.backtest import router as backtest_router
# from app.api.v1.debate import router as debate_router
# from app.api.v1.notifications import router as notifications_router
# from app.api.v1.books import router as books_router
