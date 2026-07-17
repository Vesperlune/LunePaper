"""
Task lifecycle manager. In-memory, restart = lost (acceptable for local app).
"""
import uuid, time, threading
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Task:
    task_id: str
    filename: str
    pdf_path: str
    page_count: int
    status: str = "pending"  # pending | translating | completed | failed
    created_at: float = field(default_factory=time.time)

    # Progress
    current_page: int = 0
    total_pages: int = 0
    pages_done: list = field(default_factory=list)

    # Results
    blocks: list = field(default_factory=list)  # all blocks across pages
    figures: list = field(default_factory=list)  # image paths
    output_path: str = ""
    quality: dict = field(default_factory=dict)
    error: str = ""

    # Cancellation
    _cancel_event: Optional[threading.Event] = None

    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "filename": self.filename,
            "status": self.status,
            "page_count": self.page_count,
            "progress": {
                "current": self.current_page,
                "total": self.total_pages,
            },
            "pages_done": self.pages_done,
            "quality": self.quality,
            "output_path": self.output_path,
            "error": self.error,
        }


class TaskManager:
    def __init__(self):
        self._tasks: dict[str, Task] = {}

    def create(self, filename: str, pdf_path: str, page_count: int) -> Task:
        task = Task(
            task_id=uuid.uuid4().hex[:12],
            filename=filename,
            pdf_path=pdf_path,
            page_count=page_count,
        )
        self._tasks[task.task_id] = task
        return task

    def get(self, task_id: str) -> Optional[Task]:
        return self._tasks.get(task_id)

    def update(self, task_id: str, **kwargs):
        task = self._tasks.get(task_id)
        if task:
            for k, v in kwargs.items():
                setattr(task, k, v)

    def set_cancel_event(self, task_id: str, event: threading.Event):
        task = self._tasks.get(task_id)
        if task:
            task._cancel_event = event

    def is_cancelled(self, task_id: str) -> bool:
        task = self._tasks.get(task_id)
        return task._cancel_event.is_set() if task and task._cancel_event else False


# Singleton
task_manager = TaskManager()
