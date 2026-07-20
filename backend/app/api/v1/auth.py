"""Auth API routes."""

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User
from app.schemas import LoginRequest, RegisterRequest, TokenResponse, UserResponse
from app.utils.exceptions import BadRequestException, UnauthorizedException
from app.utils.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)

router = APIRouter(prefix="/auth", tags=["auth"])


async def get_current_user(
    authorization: str = Header(default=""),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Dependency: extract and validate JWT from Authorization header.

    Also enforces account-active status so a disabled user's still-valid token
    (within its 24h lifetime) is rejected instead of silently honoured.
    """
    if not authorization.startswith("Bearer "):
        raise UnauthorizedException("Missing or invalid Authorization header")
    token = authorization[7:]
    payload = decode_access_token(token)
    if payload is None:
        raise UnauthorizedException("Invalid or expired token")
    user_id = int(payload.get("sub", 0))
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise UnauthorizedException("User not found")
    if not user.is_active:
        raise UnauthorizedException("User account is disabled")
    return user


async def require_admin(current_user: User = Depends(get_current_user)) -> User:
    """Dependency: require admin role. Single source of truth for admin gating."""
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return current_user


@router.post("/login", response_model=TokenResponse)
async def login(req: LoginRequest, db: AsyncSession = Depends(get_db)):
    """登录，支持邮箱或用户名登录 + 密码错误次数限制（idea28）。

    连续 5 次错误锁定 15 分钟。
    """
    import time
    # 密码错误次数限制（内存简易实现；生产级应用 Redis）
    _lock_threshold = 5
    _lock_minutes = 15
    now = time.time()
    key = req.username.lower()
    if key in _login_fail_count:
        count, locked_until = _login_fail_count[key]
        if locked_until and now < locked_until:
            raise UnauthorizedException(f"账号已被锁定，请 {_lock_minutes} 分钟后再试")

    result = await db.execute(
        select(User).where((User.username == req.username) | (User.email == req.username))
    )
    user = result.scalar_one_or_none()
    if not user or not verify_password(req.password, user.password_hash):
        count = _login_fail_count.get(key, (0, 0))[0] + 1
        locked_until = now + _lock_minutes * 60 if count >= _lock_threshold else 0
        _login_fail_count[key] = (count, locked_until)
        remaining = _lock_threshold - count
        msg = f"用户名或密码错误（剩余 {remaining} 次尝试）" if remaining > 0 else f"账号已锁定 {_lock_minutes} 分钟"
        raise UnauthorizedException(msg)

    # 登录成功 → 清除失败计数
    _login_fail_count.pop(key, None)
    token = create_access_token({"sub": str(user.id), "role": user.role})
    return TokenResponse(access_token=token)


# 密码错误计数：{username/email: (count, locked_until_timestamp)}
_login_fail_count: dict[str, tuple[int, float]] = {}


@router.post("/register", response_model=UserResponse)
async def register(req: RegisterRequest, db: AsyncSession = Depends(get_db)):
    """注册——邮箱作为ID + 用户名 + 重名检测（idea28）。

    - email 必须为有效邮箱格式且唯一
    - username 重名检测
    - 密码 >= 8 位
    """
    import re

    # 邮箱格式校验
    if not re.match(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$", req.email):
        raise BadRequestException("邮箱格式不正确")

    # 邮箱唯一性
    existing_email = await db.execute(select(User).where(User.email == req.email))
    if existing_email.scalar_one_or_none():
        raise BadRequestException("该邮箱已注册")

    # 用户名重名检测
    existing_name = await db.execute(select(User).where(User.username == req.username))
    if existing_name.scalar_one_or_none():
        raise BadRequestException("用户名已存在")

    user = User(
        username=req.username,
        email=req.email,
        password_hash=hash_password(req.password),
        role="user",
    )
    db.add(user)
    await db.flush()
    await db.refresh(user)
    return user


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_user)):
    return current_user
