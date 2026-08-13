"""
Task lifecycle manager with disk persistence for completed tasks.
"""
import os, json, uuid, time, shutil, threading
from dataclasses import dataclass, field, asdict
from typing import Optional

_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_HISTORY_DIR = os.path.join(_BASE, "history")


def _history_dir() -> str:
    os.makedirs(_HISTORY_DIR, exist_ok=True)
    return _HISTORY_DIR


def _task_dir(task_id: str) -> str:
    return os.path.join(_history_dir(), task_id)


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
    figures: list = field(default_factory=list)  # image paths (basenames in history)
    output_path: str = ""
    quality: dict = field(default_factory=dict)
    error: str = ""

    # Cancellation
    _cancel_event: Optional[threading.Event] = field(default=None, repr=False, compare=False)

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
        self._load_history_on_startup()

    # ── In-memory operations ──

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

    # ── Persistence ──

    def save_task(self, task_id: str):
        """Save completed task data to disk."""
        task = self._tasks.get(task_id)
        if not task:
            return
        td = _task_dir(task_id)
        os.makedirs(td, exist_ok=True)

        # Save metadata + blocks
        data = {
            "task_id": task.task_id,
            "filename": task.filename,
            "page_count": task.page_count,
            "created_at": task.created_at,
            "quality": task.quality,
            "blocks": task.blocks,
            "figures": [os.path.basename(f) for f in task.figures],
        }
        with open(os.path.join(td, "meta.json"), "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)

        # Copy figure images to history dir
        fig_dir = os.path.join(td, "figures")
        os.makedirs(fig_dir, exist_ok=True)
        import tempfile
        src_fig_dir = os.path.join(tempfile.gettempdir(), f"ppt_{task_id}_figures")
        if os.path.isdir(src_fig_dir):
            for fname in os.listdir(src_fig_dir):
                src = os.path.join(src_fig_dir, fname)
                dst = os.path.join(fig_dir, fname)
                if os.path.isfile(src) and not os.path.exists(dst):
                    shutil.copy2(src, dst)

        # Copy page images (thumbnails/comparison) to history dir
        pages_dir = os.path.join(td, "pages")
        os.makedirs(pages_dir, exist_ok=True)
        src_pages_dir = os.path.join(tempfile.gettempdir(), f"ppt_{task_id}_pages")
        if os.path.isdir(src_pages_dir):
            for fname in os.listdir(src_pages_dir):
                src = os.path.join(src_pages_dir, fname)
                dst = os.path.join(pages_dir, fname)
                if os.path.isfile(src) and not os.path.exists(dst):
                    shutil.copy2(src, dst)

    def _load_history_on_startup(self):
        """Load metadata of all saved tasks (lazy-load blocks on demand)."""
        if not os.path.isdir(_HISTORY_DIR):
            return
        for name in os.listdir(_HISTORY_DIR):
            td = os.path.join(_HISTORY_DIR, name)
            meta_path = os.path.join(td, "meta.json")
            if not os.path.isfile(meta_path):
                continue
            try:
                with open(meta_path, encoding="utf-8") as f:
                    data = json.load(f)
                task = Task(
                    task_id=data["task_id"],
                    filename=data["filename"],
                    pdf_path="",  # original PDF may be gone
                    page_count=data["page_count"],
                    status="completed",
                    created_at=data.get("created_at", 0),
                    quality=data.get("quality", {}),
                )
                # Store figure paths relative to history dir
                task.figures = [
                    os.path.join(td, "figures", fname)
                    for fname in data.get("figures", [])
                ]
                self._tasks[task.task_id] = task
            except Exception:
                continue

    def load_task_blocks(self, task_id: str) -> Optional[Task]:
        """Load full blocks data for a history task into memory."""
        task = self._tasks.get(task_id)
        if not task:
            return None
        if task.blocks:
            return task  # already loaded
        td = _task_dir(task_id)
        meta_path = os.path.join(td, "meta.json")
        if not os.path.isfile(meta_path):
            return None
        with open(meta_path, encoding="utf-8") as f:
            data = json.load(f)
        task.blocks = data.get("blocks", [])
        return task

    def delete_task(self, task_id: str) -> bool:
        """Delete task data from disk and memory."""
        td = _task_dir(task_id)
        if os.path.isdir(td):
            shutil.rmtree(td)
        self._tasks.pop(task_id, None)
        return True

    def list_history(self) -> list[dict]:
        """List all saved tasks with basic info."""
        result = []
        for tid, task in self._tasks.items():
            td = _task_dir(tid)
            if not os.path.isdir(td):
                continue
            result.append({
                "task_id": tid,
                "filename": task.filename,
                "page_count": task.page_count,
                "created_at": task.created_at,
                "quality": task.quality,
                "status": task.status,
            })
        # Sort by created_at descending (newest first)
        result.sort(key=lambda x: x["created_at"], reverse=True)
        return result


# Singleton
task_manager = TaskManager()
