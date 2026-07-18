"""Notification API routes."""

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.auth import get_current_user
from app.database import get_db
from app.models.notification import Alert, Notification
from app.models.user import User
from app.schemas import AlertCreateRequest, AlertResponse, NotificationResponse
from app.services.llm.manager import llm_manager
from app.services.notification.service import AlertEngine
from app.utils.exceptions import NotFoundException

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("", response_model=list[NotificationResponse])
async def list_notifications(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Notification)
        .where(Notification.user_id == current_user.id)
        .order_by(Notification.created_at.desc())
        .limit(50)
    )
    return result.scalars().all()


@router.get("/unread-count")
async def unread_count(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Notification).where(
            Notification.user_id == current_user.id,
            Notification.is_read == False,
        )
    )
    return {"count": len(result.scalars().all())}


@router.put("/{notification_id}/read")
async def mark_read(
    notification_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    n = await db.get(Notification, notification_id)
    if n:
        n.is_read = True
    return {"status": "ok"}


@router.put("/read-all")
async def mark_all_read(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Notification).where(
            Notification.user_id == current_user.id,
            Notification.is_read == False,
        )
    )
    for n in result.scalars():
        n.is_read = True
    return {"status": "ok"}


# --- Alerts ---
@router.post("/alerts", response_model=AlertResponse)
async def create_alert(
    req: AlertCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    engine = AlertEngine(db, llm_manager.get())
    return await engine.create_alert(
        current_user.id, req.name, req.nl_condition,
        req.target_type, req.target_id,
    )


@router.get("/alerts", response_model=list[AlertResponse])
async def list_alerts(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Alert).where(Alert.user_id == current_user.id).order_by(Alert.created_at.desc())
    )
    return result.scalars().all()


@router.put("/alerts/{alert_id}/toggle")
async def toggle_alert(
    alert_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    alert = await db.get(Alert, alert_id)
    if not alert:
        raise NotFoundException(f"Alert {alert_id} not found")
    alert.is_active = not alert.is_active
    return {"id": alert_id, "is_active": alert.is_active}


@router.delete("/alerts/{alert_id}")
async def delete_alert(
    alert_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    alert = await db.get(Alert, alert_id)
    if not alert:
        raise NotFoundException(f"Alert {alert_id} not found")
    await db.delete(alert)
    return {"status": "deleted"}
