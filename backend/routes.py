"""REST API routes."""
import os, io, shutil, tempfile, threading
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
    """Download bilingual HTML with embedded images."""
    import base64

    task = task_manager.get(task_id)
    if not task:
        raise HTTPException(404, "Task not found")
    if task.status != "completed":
        raise HTTPException(400, "Translation not completed yet")

    # Build figure lookup: basename -> base64 data URI
    fig_data = {}
    for fig_path in task.figures:
        if os.path.exists(fig_path):
            with open(fig_path, "rb") as f:
                b64 = base64.b64encode(f.read()).decode("ascii")
            fig_data[os.path.basename(fig_path)] = f"data:image/png;base64,{b64}"

    # Build HTML
    parts = []
    parts.append(f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{_esc(task.filename)} - LunePaper</title>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/katex.min.css">
<script defer src="https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/katex.min.js"></script>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, "Noto Sans SC", sans-serif;
    background: #faf8ff;
    color: #2d2a3e;
    line-height: 1.7;
    padding: 2rem;
    max-width: 960px;
    margin: 0 auto;
  }}
  .header {{
    text-align: center;
    padding: 2rem 0 1.5rem;
    border-bottom: 2px solid #e8e3f3;
    margin-bottom: 2rem;
  }}
  .header h1 {{
    font-size: 1.6rem;
    color: #5b4ea8;
    font-weight: 700;
    margin-bottom: 0.5rem;
  }}
  .header .meta {{
    font-size: 0.85rem;
    color: #8b85a3;
  }}
  .page-break {{
    display: flex;
    align-items: center;
    gap: 1rem;
    margin: 2.5rem 0 1.5rem;
  }}
  .page-break .badge {{
    display: inline-flex;
    align-items: center;
    gap: 0.4rem;
    padding: 0.3rem 0.9rem;
    border-radius: 999px;
    background: #f3f0fa;
    border: 1px solid #e8e3f3;
    font-size: 0.85rem;
    font-weight: 600;
    color: #7c6cb8;
    white-space: nowrap;
  }}
  .page-break .line {{
    flex: 1;
    height: 1px;
    background: linear-gradient(to right, #c4b8e0, transparent);
  }}
  .block {{
    margin: 0.8rem 0;
    padding: 1rem 1.2rem;
    border-radius: 12px;
    background: #fff;
    border: 1px solid #f0ecf8;
    box-shadow: 0 1px 4px rgba(139,127,199,0.04);
  }}
  .block-type {{
    display: inline-block;
    font-size: 0.7rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: #8b7fc7;
    background: #f3f0fa;
    padding: 0.15rem 0.5rem;
    border-radius: 4px;
    margin-bottom: 0.5rem;
  }}
  .en {{
    font-size: 0.95rem;
    color: #8b85a3;
    font-style: italic;
    line-height: 1.7;
    padding-bottom: 0.6rem;
  }}
  .zh {{
    font-size: 1rem;
    color: #2d2a3e;
    line-height: 1.8;
    border-top: 1px solid #f0ecf8;
    padding-top: 0.6rem;
  }}
  .zh.error {{
    color: #c47a7a;
    font-style: italic;
  }}
  .title-text {{
    font-size: 1.25rem;
    font-weight: 700;
    color: #2d2a3e;
    line-height: 1.5;
  }}
  .title-text.en {{
    color: #5a5475;
    font-style: italic;
  }}
  .figure {{
    text-align: center;
    margin: 1.2rem 0;
  }}
  .figure img {{
    max-width: 100%;
    border-radius: 12px;
    border: 1px solid #f0ecf8;
    box-shadow: 0 2px 12px rgba(139,127,199,0.08);
  }}
  .figure .caption {{
    font-size: 0.85rem;
    color: #8b85a3;
    margin-top: 0.5rem;
  }}
  .passthrough {{
    font-size: 0.95rem;
    color: #2d2a3e;
    line-height: 1.7;
  }}
  .separator {{
    height: 1px;
    background: linear-gradient(to right, #e8e3f3, transparent);
    margin: 0.4rem 0;
  }}
  .katex-display {{
    margin: 0.5rem 0;
    overflow-x: auto;
    overflow-y: hidden;
    padding: 0.3rem 0;
  }}
  .katex {{
    font-size: 1.05em;
  }}
  @media print {{
    body {{ padding: 1rem; }}
    .block {{ break-inside: avoid; }}
  }}
</style>
</head>
<body>
<div class="header">
  <h1>{_esc(task.filename)}</h1>
  <div class="meta">{task.quality.get('total_blocks', '?')} 个内容块 | 通过率: {task.quality.get('pass_rate', 'N/A')}</div>
</div>
""")

    current_page = 0
    for block in task.blocks:
        if block['page'] != current_page:
            current_page = block['page']
            parts.append(f'<div class="page-break"><span class="badge">第 {current_page} 页</span><span class="line"></span></div>\n')

        btype = block['type']
        en = block.get('en', '')
        zh = block.get('zh', '')

        # Image / Chart blocks
        if btype in ('image', 'chart', 'figure'):
            fig_id = block.get('figure_id', '')
            if fig_id and fig_id in fig_data:
                parts.append(f'<div class="figure"><img src="{fig_data[fig_id]}" alt="Figure" /><div class="caption">[{_esc(btype)}]</div></div>\n')
            else:
                parts.append(f'<div class="figure"><div class="caption">[{_esc(btype)}] (图片未找到)</div></div>\n')
            continue

        # Equation blocks — store LaTeX in data attribute, render with KaTeX JS
        if btype == 'equation':
            # Strip $$ delimiters (KaTeX displayMode handles formatting)
            latex = en.strip()
            if latex.startswith('$$'):
                latex = latex[2:]
            if latex.endswith('$$'):
                latex = latex[:-2]
            latex = latex.strip()
            # Sanitize for HTML attribute: collapse whitespace, escape special chars
            latex = latex.replace('\n', ' ').replace('\r', ' ')
            latex = ' '.join(latex.split())  # collapse multiple spaces
            latex = latex.replace('&', '&amp;').replace('"', '&quot;').replace('<', '&lt;').replace('>', '&gt;')
            parts.append(f'<div class="block"><div class="block-type">equation</div><div class="math-block" data-latex="{latex}"></div></div>\n')
            continue

        # Table blocks
        if btype == 'table':
            parts.append(f'<div class="block"><div class="block-type">table</div><div class="passthrough">{en}</div></div>\n')
            continue

        # Title blocks — larger font
        if btype == 'title':
            parts.append(f'<div class="block"><div class="title-text en">{_esc(en)}</div>')
            if zh and zh != en:
                if zh.startswith('[ERROR'):
                    parts.append(f'<div class="zh error">{_esc(zh)}</div>')
                else:
                    parts.append(f'<div class="separator"></div><div class="title-text">{_esc(zh)}</div>')
            parts.append('</div>\n')
            continue

        # Passthrough types (ref_text, aside_text, header, footer, algorithm, image_caption, image_footnote)
        if block.get('passthrough') or btype in ('ref_text', 'aside_text', 'header', 'footer', 'algorithm', 'image_caption', 'image_footnote'):
            parts.append(f'<div class="block"><span class="block-type">{_esc(btype)}</span><div class="passthrough">{_esc(en)}</div>')
            if zh and zh != en and not zh.startswith('[ERROR'):
                parts.append(f'<div class="separator"></div><div class="passthrough">{_esc(zh)}</div>')
            parts.append('</div>\n')
            continue

        # Normal text blocks — bilingual
        parts.append(f'<div class="block">')
        if btype != 'text':
            parts.append(f'<span class="block-type">{_esc(btype)}</span>')
        parts.append(f'<div class="en">{_esc(en)}</div>')
        if zh:
            if zh.startswith('[ERROR'):
                parts.append(f'<div class="separator"></div><div class="zh error">{_esc(zh)}</div>')
            elif zh != en:
                parts.append(f'<div class="separator"></div><div class="zh">{_esc(zh)}</div>')
        parts.append('</div>\n')

    parts.append('<script>')
    parts.append('document.addEventListener("DOMContentLoaded", function() {')
    parts.append('  // Render standalone equation blocks from data-latex')
    parts.append('  document.querySelectorAll(".math-block").forEach(function(el) {')
    parts.append('    var latex = el.getAttribute("data-latex");')
    parts.append('    if (latex && typeof katex !== "undefined") {')
    parts.append('      katex.render(latex, el, { displayMode: true, throwOnError: false });')
    parts.append('    } else if (latex) { el.textContent = latex; }')
    parts.append('  });')
    parts.append('  // Render inline math $...$ within text content')
    parts.append('  if (typeof katex !== "undefined") {')
    parts.append('    var unesc = function(s) { return s.replace(/&amp;/g,"&").replace(/&lt;/g,"<").replace(/&gt;/g,">").replace(/&quot;/g,\'"\'); };')
    parts.append('    document.querySelectorAll(".en, .zh, .passthrough, .title-text").forEach(function(el) {')
    parts.append('      var html = el.innerHTML;')
    parts.append('      if (html.indexOf("$") === -1) return;')
    parts.append('      var result = html.replace(/\\$([^\\$\\n]+?)\\$/g, function(m, latex) {')
    parts.append('        try { return katex.renderToString(unesc(latex), { throwOnError: false }); }')
    parts.append('        catch(e) { return m; }')
    parts.append('      });')
    parts.append('      if (result !== html) el.innerHTML = result;')
    parts.append('    });')
    parts.append('  }')
    parts.append('});')
    parts.append('</script>')
    parts.append('</body>\n</html>')

    html = ''.join(parts)
    buf = io.BytesIO(html.encode('utf-8'))
    raw_name = os.path.splitext(task.filename)[0] + "_bilingual.html"
    # Percent-encode filename for HTTP header (latin-1 safe)
    from urllib.parse import quote
    encoded_name = quote(raw_name, safe='')
    return StreamingResponse(
        buf, media_type="text/html; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{encoded_name}"})


def _esc(s: str) -> str:
    """Escape HTML special characters."""
    return (s.replace("&", "&amp;")
             .replace("<", "&lt;")
             .replace(">", "&gt;")
             .replace('"', "&quot;"))


@router.get("/history")
async def list_history():
    """List all saved translation history."""
    return task_manager.list_history()


@router.post("/history/{task_id}/load")
async def load_history_task(task_id: str):
    """Load a history task's blocks into memory for viewing."""
    task = task_manager.load_task_blocks(task_id)
    if not task:
        raise HTTPException(404, "History task not found")
    result = task.to_dict()
    result["blocks"] = task.blocks
    result["figures"] = [os.path.basename(f) for f in task.figures]
    return result


@router.delete("/history/{task_id}")
async def delete_history_task(task_id: str):
    """Delete a history task and its data from disk."""
    task_manager.delete_task(task_id)
    return {"status": "deleted"}


@router.get("/image/{task_id}/{figure_name}")
async def get_figure(task_id: str, figure_name: str):
    """Serve a cropped figure image from temp or history directory."""
    # Try temp dir first (active tasks)
    fig_dir = os.path.join(tempfile.gettempdir(), f"ppt_{task_id}_figures")
    fig_path = os.path.join(fig_dir, figure_name)
    if os.path.exists(fig_path):
        return FileResponse(fig_path, media_type="image/png")
    # Try history dir (loaded history tasks)
    from backend.task_manager import _task_dir
    hist_fig = os.path.join(_task_dir(task_id), "figures", figure_name)
    if os.path.exists(hist_fig):
        return FileResponse(hist_fig, media_type="image/png")
    raise HTTPException(404, "Figure not found")


@router.get("/page-image/{task_id}/{page_num}")
async def get_page_image(task_id: str, page_num: int, dpi: int = 72):
    """Render and serve a single PDF page image.
    page_num is 1-indexed (matches the UI).
    dpi controls resolution: 72 for thumbnails, 150+ for comparison view."""
    dpi = min(max(dpi, 36), 300)  # clamp to safe range

    # Check history dir first (for loaded history tasks)
    from backend.task_manager import _task_dir
    hist_page = os.path.join(_task_dir(task_id), "pages", f"page_{page_num}_dpi{dpi}.png")
    if os.path.exists(hist_page):
        return FileResponse(hist_page, media_type="image/png")

    # Check temp dir (for active tasks)
    page_dir = os.path.join(tempfile.gettempdir(), f"ppt_{task_id}_pages")
    page_path = os.path.join(page_dir, f"page_{page_num}_dpi{dpi}.png")
    if os.path.exists(page_path):
        return FileResponse(page_path, media_type="image/png")

    # Render from PDF if available
    task = task_manager.get(task_id)
    if not task or not task.pdf_path:
        raise HTTPException(404, "Page image not available")

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
