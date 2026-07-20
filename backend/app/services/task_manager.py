"""Task manager for tracking long-running background tasks."""

import asyncio
import threading
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum


class TaskStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    STOPPED = "stopped"


@dataclass
class TaskProgress:
    """Task progress information."""

    task_id: str
    task_type: str
    status: TaskStatus
    progress: float = 0.0  # 0.0 to 100.0
    current: int = 0
    total: int = 0
    message: str = ""
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error: str | None = None
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "task_type": self.task_type,
            "status": self.status.value,
            "progress": round(self.progress, 2),
            "current": self.current,
            "total": self.total,
            "message": self.message,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "error": self.error,
            "metadata": self.metadata,
        }


class TaskManager:
    """Manages background tasks with progress tracking and control."""

    def __init__(self):
        self._tasks: dict[str, TaskProgress] = {}
        self._pause_events: dict[str, threading.Event] = {}
        self._stop_flags: dict[str, bool] = {}
        self._subscribers: dict[str, list[asyncio.Queue]] = {}
        self._lock = threading.Lock()

    def create_task(self, task_id: str, task_type: str, total: int = 0) -> TaskProgress:
        """Create a new task."""
        with self._lock:
            progress = TaskProgress(
                task_id=task_id,
                task_type=task_type,
                status=TaskStatus.PENDING,
                total=total,
                started_at=datetime.now(),
            )
            self._tasks[task_id] = progress
            self._pause_events[task_id] = threading.Event()
            self._pause_events[task_id].set()  # Not paused initially
            self._stop_flags[task_id] = False
            self._subscribers[task_id] = []
            return progress

    def update_progress(
        self,
        task_id: str,
        current: int | None = None,
        message: str | None = None,
        metadata: dict | None = None,
    ) -> TaskProgress | None:
        """Update task progress."""
        with self._lock:
            if task_id not in self._tasks:
                return None

            task = self._tasks[task_id]

            # Auto-transition from PENDING to RUNNING on first update
            if task.status == TaskStatus.PENDING:
                task.status = TaskStatus.RUNNING

            if current is not None:
                task.current = current
                if task.total > 0:
                    task.progress = (current / task.total) * 100.0

            if message is not None:
                task.message = message

            if metadata is not None:
                task.metadata.update(metadata)

            # Notify subscribers
            self._notify_subscribers(task_id, task)

            return task

    def complete_task(self, task_id: str, message: str = "Completed") -> TaskProgress | None:
        """Mark task as completed."""
        with self._lock:
            if task_id not in self._tasks:
                return None

            task = self._tasks[task_id]
            task.status = TaskStatus.COMPLETED
            task.progress = 100.0
            task.message = message
            task.completed_at = datetime.now()

            self._notify_subscribers(task_id, task)
            return task

    def fail_task(self, task_id: str, error: str) -> TaskProgress | None:
        """Mark task as failed."""
        with self._lock:
            if task_id not in self._tasks:
                return None

            task = self._tasks[task_id]
            task.status = TaskStatus.FAILED
            task.error = error
            task.completed_at = datetime.now()

            self._notify_subscribers(task_id, task)
            return task

    def pause_task(self, task_id: str) -> bool:
        """Pause a running task."""
        with self._lock:
            if task_id not in self._tasks:
                return False

            task = self._tasks[task_id]
            if task.status != TaskStatus.RUNNING:
                return False

            task.status = TaskStatus.PAUSED
            task.message = "Paused"
            self._pause_events[task_id].clear()

            self._notify_subscribers(task_id, task)
            return True

    def resume_task(self, task_id: str) -> bool:
        """Resume a paused task."""
        with self._lock:
            if task_id not in self._tasks:
                return False

            task = self._tasks[task_id]
            if task.status != TaskStatus.PAUSED:
                return False

            task.status = TaskStatus.RUNNING
            task.message = "Resumed"
            self._pause_events[task_id].set()

            self._notify_subscribers(task_id, task)
            return True

    def stop_task(self, task_id: str) -> bool:
        """Stop a task."""
        with self._lock:
            if task_id not in self._tasks:
                return False

            task = self._tasks[task_id]
            if task.status in [TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.STOPPED]:
                return False

            task.status = TaskStatus.STOPPED
            task.message = "Stopped by user"
            task.completed_at = datetime.now()
            self._stop_flags[task_id] = True
            self._pause_events[task_id].set()  # Unblock if paused

            self._notify_subscribers(task_id, task)
            return True

    def get_task(self, task_id: str) -> TaskProgress | None:
        """Get task progress."""
        with self._lock:
            return self._tasks.get(task_id)

    def list_tasks(self) -> list[TaskProgress]:
        """List all tasks."""
        with self._lock:
            return list(self._tasks.values())

    def check_pause_stop(self, task_id: str) -> tuple[bool, bool]:
        """Check if task should pause or stop. Returns (should_pause, should_stop)."""
        if task_id not in self._tasks:
            return False, True

        should_stop = self._stop_flags.get(task_id, False)
        should_pause = not self._pause_events[task_id].is_set()

        return should_pause, should_stop

    def wait_if_paused(self, task_id: str, timeout: float = 1.0) -> bool:
        """Wait if task is paused. Returns True if should continue, False if should stop."""
        if task_id not in self._tasks:
            return False

        # Wait for pause event (blocks if paused)
        while not self._pause_events[task_id].wait(timeout=timeout):
            # Check if stopped while paused
            if self._stop_flags.get(task_id, False):
                return False

        # Check if stopped
        if self._stop_flags.get(task_id, False):
            return False

        return True

    def subscribe(self, task_id: str) -> asyncio.Queue:
        """Subscribe to task progress updates."""
        queue = asyncio.Queue()
        with self._lock:
            if task_id in self._subscribers:
                self._subscribers[task_id].append(queue)
        return queue

    def unsubscribe(self, task_id: str, queue: asyncio.Queue):
        """Unsubscribe from task progress updates."""
        with self._lock:
            if task_id in self._subscribers:
                if queue in self._subscribers[task_id]:
                    self._subscribers[task_id].remove(queue)

    def _notify_subscribers(self, task_id: str, task: TaskProgress):
        """Notify all subscribers of task update."""
        if task_id in self._subscribers:
            for queue in self._subscribers[task_id]:
                try:
                    queue.put_nowait(task.to_dict())
                except asyncio.QueueFull:
                    pass  # Drop update if queue is full

    def cleanup_task(self, task_id: str):
        """Remove task from manager."""
        with self._lock:
            self._tasks.pop(task_id, None)
            self._pause_events.pop(task_id, None)
            self._stop_flags.pop(task_id, None)
            self._subscribers.pop(task_id, None)


# Global task manager instance
task_manager = TaskManager()
