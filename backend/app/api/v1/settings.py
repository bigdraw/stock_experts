"""Settings API endpoints."""

import logging
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.auth import get_current_user, require_admin
from app.database import get_db
from app.models.user import User
from app.services.data.akshare_provider import get_proxy_enabled, set_proxy_enabled, AkShareProvider
from app.services import settings_service

logger = logging.getLogger(__name__)

# All settings endpoints mutate or expose sensitive runtime config (LLM api_key,
# proxy toggles, data-source, backtest friction). Admin-only at the router level
# so no endpoint can accidentally be left open.
router = APIRouter(
    prefix="/settings",
    tags=["settings"],
    dependencies=[Depends(require_admin)],
)


# ========== Proxy Settings ==========

class ProxySettingRequest(BaseModel):
    enabled: bool


class ProxySettingResponse(BaseModel):
    enabled: bool


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


class TestConnectionResponse(BaseModel):
    success: bool
    message: str


@router.post("/test-connection", response_model=TestConnectionResponse)
async def test_connection(current_user: User = Depends(get_current_user)):
    """Test data source connection."""
    provider = AkShareProvider()
    try:
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


# ========== LLM Settings ==========

class LLMConfigRequest(BaseModel):
    provider: str
    base_url: str
    api_key: str
    model: str
    max_tokens: int = 65536
    temperature: float = 0.7


class LLMConfigResponse(BaseModel):
    provider: str
    base_url: str
    api_key: str  # Masked for display
    model: str
    max_tokens: int
    temperature: float


def _mask_api_key(api_key: str) -> str:
    """Mask API key for display: show first 4 and last 4 chars."""
    if not api_key or len(api_key) <= 8:
        return "****"
    return f"{api_key[:4]}****{api_key[-4:]}"


@router.get("/llm", response_model=LLMConfigResponse)
async def get_llm_setting(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get LLM configuration (API key masked)."""
    config = await settings_service.get_llm_config(db)
    return LLMConfigResponse(
        provider=config["provider"],
        base_url=config["base_url"],
        api_key=_mask_api_key(config.get("api_key", "")),
        model=config["model"],
        max_tokens=config["max_tokens"],
        temperature=config["temperature"],
    )


@router.put("/llm", response_model=LLMConfigResponse)
async def set_llm_setting(
    request: LLMConfigRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update LLM configuration."""
    # If api_key is masked, keep the existing one
    existing = await settings_service.get_llm_config(db)
    if "****" in request.api_key:
        request.api_key = existing.get("api_key", "")

    config = {
        "provider": request.provider,
        "base_url": request.base_url,
        "api_key": request.api_key,
        "model": request.model,
        "max_tokens": request.max_tokens,
        "temperature": request.temperature,
    }
    await settings_service.set_llm_config(db, config)

    return LLMConfigResponse(
        provider=config["provider"],
        base_url=config["base_url"],
        api_key=_mask_api_key(config["api_key"]),
        model=config["model"],
        max_tokens=config["max_tokens"],
        temperature=config["temperature"],
    )


@router.post("/test-llm", response_model=TestConnectionResponse)
async def test_llm_connection(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Test LLM connection with current configuration."""
    from app.services.llm.openai_compatible import OpenAICompatibleProvider

    config = await settings_service.get_llm_config(db)
    api_key = config.get("api_key", "")
    if not api_key:
        return TestConnectionResponse(success=False, message="API Key 未配置")

    try:
        provider = OpenAICompatibleProvider(
            base_url=config["base_url"],
            api_key=api_key,
            model=config["model"],
        )
        ok = await provider.health_check()
        await provider.close()
        if ok:
            return TestConnectionResponse(success=True, message=f"LLM 连接成功 ({config['model']})")
        else:
            return TestConnectionResponse(success=False, message="LLM 连接失败")
    except Exception as e:
        return TestConnectionResponse(success=False, message=f"LLM 连接失败: {str(e)}")


# ========== Data Source Settings ==========

class DataSourceConfigRequest(BaseModel):
    provider: str
    rate_limit: int = 10
    retry_max: int = 3


class DataSourceConfigResponse(BaseModel):
    provider: str
    rate_limit: int
    retry_max: int


@router.get("/data-source", response_model=DataSourceConfigResponse)
async def get_data_source_setting(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get data source configuration."""
    config = await settings_service.get_data_source_config(db)
    return DataSourceConfigResponse(**config)


@router.put("/data-source", response_model=DataSourceConfigResponse)
async def set_data_source_setting(
    request: DataSourceConfigRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update data source configuration."""
    config = request.model_dump()
    await settings_service.set_data_source_config(db, config)
    return DataSourceConfigResponse(**config)


# ========== Friction Cost Settings ==========

class FrictionConfigRequest(BaseModel):
    stamp_tax: float = 0.0005
    commission: float = 0.00025
    commission_min: float = 5.0
    slippage: float = 0.001


class FrictionConfigResponse(BaseModel):
    stamp_tax: float
    commission: float
    commission_min: float
    slippage: float


@router.get("/friction", response_model=FrictionConfigResponse)
async def get_friction_setting(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get backtest friction configuration."""
    config = await settings_service.get_friction_config(db)
    return FrictionConfigResponse(**config)


@router.put("/friction", response_model=FrictionConfigResponse)
async def set_friction_setting(
    request: FrictionConfigRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update backtest friction configuration."""
    config = request.model_dump()
    await settings_service.set_friction_config(db, config)
    return FrictionConfigResponse(**config)
