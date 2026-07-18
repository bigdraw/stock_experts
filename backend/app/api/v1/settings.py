"""Settings API endpoints."""

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.api.v1.auth import get_current_user
from app.models.user import User
from app.services.data.akshare_provider import get_proxy_enabled, set_proxy_enabled, AkShareProvider

router = APIRouter(prefix="/settings", tags=["settings"])


class ProxySettingRequest(BaseModel):
    enabled: bool


class ProxySettingResponse(BaseModel):
    enabled: bool


class TestConnectionResponse(BaseModel):
    success: bool
    message: str


@router.get("/proxy", response_model=ProxySettingResponse)
async def get_proxy_setting(current_user: User = Depends(get_current_user)):
    """Get proxy enabled setting."""
    enabled = await get_proxy_enabled()
    return ProxySettingResponse(enabled=enabled)


@router.put("/proxy", response_model=ProxySettingResponse)
async def set_proxy_setting(
    request: ProxySettingRequest,
    current_user: User = Depends(get_current_user),
):
    """Set proxy enabled setting."""
    await set_proxy_enabled(request.enabled)
    return ProxySettingResponse(enabled=request.enabled)


@router.post("/test-connection", response_model=TestConnectionResponse)
async def test_connection(current_user: User = Depends(get_current_user)):
    """Test data source connection."""
    provider = AkShareProvider()
    try:
        # Try to fetch a small amount of data
        stocks = await provider.get_stock_list()
        if stocks and len(stocks) > 0:
            return TestConnectionResponse(
                success=True, 
                message=f"连接成功，获取到 {len(stocks)} 只股票"
            )
        else:
            return TestConnectionResponse(
                success=False, 
                message="连接成功但未获取到数据"
            )
    except Exception as e:
        return TestConnectionResponse(
            success=False, 
            message=f"连接失败: {str(e)}"
        )
