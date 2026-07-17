"""REST API routes."""
import os, io, shutil, zipfile, tempfile, threading
from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

from backend.task_manager import task_manager

router = APIRouter(prefix="/api")
UPLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "uploads")


from config import get as cfg

class TranslateRequest(BaseModel):
    dpi: int = cfg('ocr', 'dpi', default=144)
    start_page: int = 0
    end_page: int | None = None


@router.post("/upload")
async def upload_pdf(file: UploadFile = File(...)):
    if not file.filename.endswith(".pdf"):
        raise HTTPException(400, "Only PDF files supported")

    os.makedirs(UPLOAD_DIR, exist_ok=True)
    task = task_manager.create(file.filename, "", 0)

    # Save file
    pdf_path = os.path.join(UPLOAD_DIR, f"{task.task_id}.pdf")
    with open(pdf_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    # Get page count
    import fitz
    doc = fitz.open(pdf_path)
    page_count = len(doc)
    doc.close()

    task_manager.update(task.task_id,
                        pdf_path=pdf_path, page_count=page_count)

    return task.to_dict()


@router.post("/translate/{task_id}")
async def start_translation(task_id: str, req: TranslateRequest = None):
    task = task_manager.get(task_id)
    if not task:
        raise HTTPException(404, "Task not found")

    if task.status == "translating":
        raise HTTPException(400, "Already translating")

    if req is None:
        req = TranslateRequest()

    # Start translation in background thread
    cancel_event = threading.Event()
    task_manager.set_cancel_event(task_id, cancel_event)
    task_manager.update(task_id, status="translating", total_pages=task.page_count)

    from backend.worker import run_translation
    thread = threading.Thread(
        target=run_translation,
        args=(task, req.dpi, cancel_event),
        daemon=True)
    thread.start()

    return {"task_id": task_id, "status": "started"}


@router.get("/status/{task_id}")
async def get_status(task_id: str):
    task = task_manager.get(task_id)
    if not task:
        raise HTTPException(404, "Task not found")
    return task.to_dict()


@router.post("/cancel/{task_id}")
async def cancel_translation(task_id: str):
    task = task_manager.get(task_id)
    if not task:
        raise HTTPException(404, "Task not found")
    if task._cancel_event:
        task._cancel_event.set()
    task_manager.update(task, status="failed", error="Cancelled by user")
    return {"status": "cancelled"}


@router.get("/download/{task_id}")
async def download_result(task_id: str):
    """Download bilingual Markdown + images as ZIP."""
    task = task_manager.get(task_id)
    if not task:
        raise HTTPException(404, "Task not found")
    if task.status != "completed":
        raise HTTPException(400, "Translation not completed yet")

    # Build Markdown
    md = f"# {task.filename}\n\n"
    md += f"> {task.quality.get('total_blocks', '?')} blocks | "
    md += f"Pass rate: {task.quality.get('pass_rate', 'N/A')}\n\n"

    current_page = 0
    for block in task.blocks:
        if block['page'] != current_page:
            current_page = block['page']
            md += f"## Page {current_page}\n\n"
        md += f"**[{block['type']}]**\n\n"
        md += f"> {block['en']}\n\n"
        zh = block.get('zh', '')
        if zh.startswith('[ERROR'):
            md += f"*{zh}*\n\n"
        else:
            md += f"{zh}\n\n"
        md += "---\n\n"

    # Create ZIP in memory
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("translation.md", md)
        for fig_path in task.figures:
            if os.path.exists(fig_path):
                zf.write(fig_path, os.path.basename(fig_path))

    buf.seek(0)
    filename = os.path.splitext(task.filename)[0] + "_bilingual.zip"
    return StreamingResponse(
        buf, media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename={filename}"})


@router.get("/image/{task_id}/{figure_name}")
async def get_figure(task_id: str, figure_name: str):
    """Serve a cropped figure image."""
    fig_dir = os.path.join(tempfile.gettempdir(), f"ppt_{task_id}_figures")
    fig_path = os.path.join(fig_dir, figure_name)
    if not os.path.exists(fig_path):
        raise HTTPException(404, "Figure not found")
    return FileResponse(fig_path, media_type="image/png")


@router.get("/page-image/{task_id}/{page_num}")
async def get_page_image(task_id: str, page_num: int, dpi: int = 72):
    """Render and serve a single PDF page image.
    page_num is 1-indexed (matches the UI).
    dpi controls resolution: 72 for thumbnails, 150+ for comparison view."""
    task = task_manager.get(task_id)
    if not task or not task.pdf_path:
        raise HTTPException(404, "Task or PDF not found")

    dpi = min(max(dpi, 36), 300)  # clamp to safe range
    page_dir = os.path.join(tempfile.gettempdir(), f"ppt_{task_id}_pages")
    page_path = os.path.join(page_dir, f"page_{page_num}_dpi{dpi}.png")

    if os.path.exists(page_path):
        return FileResponse(page_path, media_type="image/png")

    import fitz
    os.makedirs(page_dir, exist_ok=True)
    doc = fitz.open(task.pdf_path)
    idx = page_num - 1
    if idx < 0 or idx >= len(doc):
        raise HTTPException(404, "Page out of range")
    pix = doc[idx].get_pixmap(dpi=dpi)
    pix.save(page_path)
    doc.close()
    return FileResponse(page_path, media_type="image/png")
