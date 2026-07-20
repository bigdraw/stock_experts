"""Admin API endpoints for user management."""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.auth import require_admin
from app.database import get_db
from app.models.user import User
from app.utils.security import hash_password

router = APIRouter(prefix="/admin", tags=["admin"])


class AdminUserResponse(BaseModel):
    """Admin view of user (includes more details)."""

    id: int
    username: str
    role: str
    is_active: bool
    created_at: str
    updated_at: str


class ResetPasswordRequest(BaseModel):
    """Request to reset user password."""

    new_password: str = Field(..., min_length=6, description="New password (min 6 characters)")


class UpdateUserRoleRequest(BaseModel):
    """Request to update user role."""

    role: str = Field(..., pattern="^(admin|user)$", description="Role must be 'admin' or 'user'")


class UpdateUserStatusRequest(BaseModel):
    """Request to enable/disable user."""

    is_active: bool = Field(..., description="Whether user account is active")


@router.get("/users", response_model=list[AdminUserResponse])
async def list_users(
    db: AsyncSession = Depends(get_db), current_user: User = Depends(require_admin)
):
    """List all users (admin only)."""
    result = await db.execute(select(User).order_by(User.created_at.desc()))
    users = result.scalars().all()

    return [
        AdminUserResponse(
            id=user.id,
            username=user.username,
            role=user.role,
            is_active=user.is_active,
            created_at=user.created_at.isoformat(),
            updated_at=user.updated_at.isoformat(),
        )
        for user in users
    ]


@router.post("/users/{user_id}/reset-password")
async def reset_user_password(
    user_id: int,
    request: ResetPasswordRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Reset user password (admin only)."""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    user.password_hash = hash_password(request.new_password)
    await db.commit()

    return {"message": f"Password reset for user {user.username}"}


@router.put("/users/{user_id}/role")
async def update_user_role(
    user_id: int,
    request: UpdateUserRoleRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Update user role (admin only)."""
    # Prevent admin from demoting themselves
    if user_id == current_user.id and request.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot demote yourself from admin"
        )

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    user.role = request.role
    await db.commit()

    return {"message": f"User {user.username} role updated to {request.role}"}


@router.put("/users/{user_id}/status")
async def update_user_status(
    user_id: int,
    request: UpdateUserStatusRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Enable or disable user account (admin only)."""
    # Prevent admin from disabling themselves
    if user_id == current_user.id and not request.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot disable your own account"
        )

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    user.is_active = request.is_active
    await db.commit()

    status_text = "enabled" if request.is_active else "disabled"
    return {"message": f"User {user.username} account {status_text}"}


@router.delete("/users/{user_id}")
async def delete_user(
    user_id: int, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_admin)
):
    """Delete user account (admin only)."""
    # Prevent admin from deleting themselves
    if user_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot delete your own account"
        )

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    username = user.username
    await db.delete(user)
    await db.commit()

    return {"message": f"User {username} deleted"}
