"""Task management API routes."""

import asyncio

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import StreamingResponse

from app.api.v1.auth import get_current_user, require_admin
from app.models.user import User
from app.services.task_manager import TaskStatus, task_manager

router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.get("")
async def list_tasks(current_user: User = Depends(get_current_user)):
    """List all tasks."""
    tasks = task_manager.list_tasks()
    return [task.to_dict() for task in tasks]


@router.get("/{task_id}")
async def get_task(task_id: str, current_user: User = Depends(get_current_user)):
    """Get task progress."""
    task = task_manager.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task.to_dict()


@router.post("/{task_id}/pause")
async def pause_task(task_id: str, current_user: User = Depends(require_admin)):
    """Pause a running task (admin only)."""
    success = task_manager.pause_task(task_id)
    if not success:
        raise HTTPException(status_code=400, detail="Cannot pause task")
    return {"status": "paused"}


@router.post("/{task_id}/resume")
async def resume_task(task_id: str, current_user: User = Depends(require_admin)):
    """Resume a paused task (admin only)."""
    success = task_manager.resume_task(task_id)
    if not success:
        raise HTTPException(status_code=400, detail="Cannot resume task")
    return {"status": "resumed"}


@router.post("/{task_id}/stop")
async def stop_task(task_id: str, current_user: User = Depends(require_admin)):
    """Stop a task (admin only)."""
    success = task_manager.stop_task(task_id)
    if not success:
        raise HTTPException(status_code=400, detail="Cannot stop task")
    return {"status": "stopped"}


@router.get("/{task_id}/stream")
async def stream_task_progress(
    task_id: str,
    token: str = None,
    authorization: str = Header(default=""),
):
    """Stream task progress via Server-Sent Events.

    Note: EventSource doesn't support custom headers, so token can be passed as query parameter.
    """
    from sqlalchemy import select

    from app.database import async_session_factory
    from app.models.user import User as UserModel
    from app.utils.security import decode_access_token

    user = None

    # Try Authorization header first
    if authorization.startswith("Bearer "):
        header_token = authorization[7:]
        payload = decode_access_token(header_token)
        if payload:
            async with async_session_factory() as db:
                result = await db.execute(
                    select(UserModel).where(UserModel.id == int(payload.get("sub", 0)))
                )
                user = result.scalar_one_or_none()

    # Fall back to query parameter token
    if not user and token:
        payload = decode_access_token(token)
        if payload:
            async with async_session_factory() as db:
                result = await db.execute(
                    select(UserModel).where(UserModel.id == int(payload.get("sub", 0)))
                )
                user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")

    task = task_manager.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    async def event_generator():
        queue = task_manager.subscribe(task_id)
        try:
            # Send initial state
            yield f"data: {task.to_dict()}\n\n"

            # Stream updates
            while True:
                try:
                    update = await asyncio.wait_for(queue.get(), timeout=30.0)
                    yield f"data: {update}\n\n"

                    # Stop streaming if task is completed/failed/stopped
                    if update.get("status") in ["completed", "failed", "stopped"]:
                        break
                except TimeoutError:
                    # Send heartbeat to keep connection alive
                    yield ": heartbeat\n\n"
        finally:
            task_manager.unsubscribe(task_id, queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        },
    )


@router.delete("/{task_id}")
async def delete_task(task_id: str, current_user: User = Depends(require_admin)):
    """Delete a completed/failed/stopped task (admin only)."""
    task = task_manager.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    if task.status in [TaskStatus.RUNNING, TaskStatus.PAUSED]:
        raise HTTPException(status_code=400, detail="Cannot delete running task")

    task_manager.cleanup_task(task_id)
    return {"status": "deleted"}
