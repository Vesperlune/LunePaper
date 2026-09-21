"""REST API routes."""
import os, io, shutil, tempfile, threading, re, zipfile
from urllib.parse import quote
from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

from backend.task_manager import task_manager

router = APIRouter(prefix="/api")
UPLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "uploads")
_gpu_lock = threading.Lock()

from config import get as cfg

class TranslateRequest(BaseModel):
    dpi: int = cfg('ocr', 'dpi', default=144)
    start_page: int = 0
    end_page: int | None = None
    ocr_model: str | None = None  # "unlimited" | "ovis"


@router.get("/ocr-models")
async def get_ocr_models():
    """Get list of registered OCR models and their disk availability."""
    from config import list_ocr_models
    return list_ocr_models()


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

    if not _gpu_lock.acquire(blocking=False):
        raise HTTPException(409, "Another translation task is currently running on the GPU. Please wait for it to finish.")

    if req is None:
        req = TranslateRequest()

    try:
        # Start translation in background thread
        cancel_event = threading.Event()
        task_manager.set_cancel_event(task_id, cancel_event)
        task_manager.update(task_id, status="translating", total_pages=task.page_count)

        from backend.worker import run_translation
        thread = threading.Thread(
            target=run_translation,
            args=(task, req.dpi, cancel_event, req.start_page, req.end_page, _gpu_lock, req.ocr_model),
            daemon=True)
        thread.start()
    except Exception:
        if _gpu_lock.locked():
            _gpu_lock.release()
        raise

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
    task_manager.update(task_id, status="failed", error="Cancelled by user")
    return {"status": "cancelled"}


def _ensure_task_tldr(task) -> dict:
    tldr = getattr(task, "tldr", {}) or {}
    if tldr and any(tldr.values()):
        return tldr
    try:
        from backend.tldr_extractor import extract_paper_tldr_from_blocks
        blocks = getattr(task, "blocks", []) or []
        extracted = extract_paper_tldr_from_blocks(blocks)
        if extracted and any(extracted.values()):
            task.tldr = extracted
            task_manager.update(task.task_id, tldr=extracted)
            task_manager.save_task(task.task_id)
            return extracted
    except Exception as e:
        print(f"  [TL;DR] Auto-extraction error for {task.task_id}: {e}")
    return {}


AFFILIATION_REGEX = re.compile(r'\b(university|college|institute|institution|department|dept\.?|laboratory|laboratories|labs?|school|center|centre|academy|faculty|corporation|inc\.?|corp\.?|llc|ltd\.?|technologies|hospital|research|google|microsoft|meta|apple|amazon|openai|deepmind|baidu|tencent|alibaba|huawei|bytedance|tsinghua|peking|stanford|mit|berkeley|cmu|harvard|oxford|cambridge|toronto|carnegie|division|telecom)\b', re.IGNORECASE)
NOTE_REGEX = re.compile(r'\b(equal contribution|correspondence|corresponding author|work performed|listing order|all authors contributed|supported by|grant|project funded|technical report)\b', re.IGNORECASE)
EMAIL_REGEX = re.compile(r'(?:\{[^}]+\}|[a-zA-Z0-9._%+-]+)@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}')
URL_REGEX = re.compile(r'https?://[^\s)]+')


def _parse_author_metadata(candidate_blocks, all_blocks=None):
    authors, affiliations, emails, urls, notes, unclassified = [], [], [], [], [], []
    zh_affiliations, zh_notes = [], []
    seen_emails, seen_affils, seen_authors, seen_urls = set(), set(), set(), set()

    # Harvest URLs and footnotes from all Page 1 blocks (e.g. GitHub repos in abstract, footnotes at bottom of page 1)
    if all_blocks:
        for b in all_blocks:
            if b.get('page') != 1:
                continue
            raw_p1 = b.get('en', '')
            raw_p1 = re.sub(r'(https?:\/\/[a-zA-Z0-9_.-]+)\s*\.\s*([a-zA-Z]{2,}[^\s)]*)', r'\1.\2', raw_p1)
            for u in URL_REGEX.findall(raw_p1):
                clean_u = re.sub(r'[.,;)]+$', '', u)
                if clean_u not in seen_urls:
                    seen_urls.add(clean_u)
                    urls.append(clean_u)
            lines_p1 = [s.strip() for s in re.split(r'[\r\n]+', raw_p1) if s.strip()]
            for lp in lines_p1:
                if NOTE_REGEX.search(lp) or ((lp.startswith('*') or lp.startswith('†')) and len(lp) > 25):
                    if lp not in notes:
                        notes.append(lp)
                        if b.get('zh') and b['zh'] != b['en'] and not b['zh'].startswith('[ERROR') and b['zh'] not in zh_notes:
                            zh_notes.append(b['zh'])

    def add_author(item):
        name = item.strip()
        if not name: return
        markers = []
        name = re.sub(
            r'\$\s*\^?\{?\\?(dagger|ddagger|\*|[0-9a-z,\s]+)\}?\s*\$',
            lambda m: (
                [markers.append('†' if x.strip()=='dagger' else '‡' if x.strip()=='ddagger' else x.strip()) for x in re.split(r'[,]+', m.group(1)) if x.strip()]
            ) and '',
            name
        )
        name = re.sub(r'\$\s*(\*|†|‡|[0-9]+)\s*\$', lambda m: markers.append(m.group(1)) or '', name)
        name = re.sub(
            r'[\s,]*([*†‡§0-9]+|\([0-9*†‡§,]+\)|\[[0-9*†‡§,]+\])[\s,]*$',
            lambda m: [markers.append(x) for x in re.findall(r'[*†‡§0-9]+', m.group(1))] and '',
            name
        ).strip()
        name = re.sub(r'[*†‡§]+$', lambda m: markers.append(m.group(0)) or '', name).strip()
        if name and 2 <= len(name) <= 50 and re.search(r'[a-zA-Z\u00C0-\u024F\u4e00-\u9fa5]', name):
            key = name.lower()
            if key not in seen_authors:
                seen_authors.add(key)
                authors.append({'name': name, 'markers': list(dict.fromkeys(markers))})
        elif item and not re.match(r'^[\s*†‡§0-9]+$', item):
            unclassified.append(item)

    def add_affil(aff, zh=None):
        clean = re.sub(r'^[0-9*†‡§,\s]+|[,\s]+$', '', aff).strip()
        if clean and clean.lower() not in seen_affils:
            seen_affils.add(clean.lower())
            affiliations.append(clean)
            if zh and zh != aff and not zh.startswith('[ERROR'):
                clean_zh = re.sub(r'^[0-9*†‡§,\s]+|[,\s]+$', '', zh).strip()
                if clean_zh and clean_zh not in zh_affiliations:
                    zh_affiliations.append(clean_zh)

    for b in candidate_blocks:
        raw = b.get('en', '')
        if b.get('type') == 'table':
            raw = re.sub(r'</td>', '\n', raw, flags=re.I)
            raw = re.sub(r'<[^>]+>', ' ', raw)
        raw = re.sub(r'(https?:\/\/[a-zA-Z0-9_.-]+)\s*\.\s*([a-zA-Z]{2,}[^\s)]*)', r'\1.\2', raw)
        lines = [s.strip() for s in re.split(r'[\r\n]+', raw) if s.strip()]
        for line in lines:
            for u in URL_REGEX.findall(line):
                clean_u = re.sub(r'[.,;)]+$', '', u)
                if clean_u not in seen_urls:
                    seen_urls.add(clean_u)
                    urls.append(clean_u)
            line = URL_REGEX.sub('', line).strip()

            for em in EMAIL_REGEX.findall(line):
                em_clean = re.sub(r'\s+', '', em)
                if em_clean not in seen_emails:
                    seen_emails.add(em_clean)
                    emails.append(em_clean)
            line = EMAIL_REGEX.sub('', line).strip()
            if not line: continue

            if NOTE_REGEX.search(line) or ((line.startswith('*') or line.startswith('†')) and len(line) > 25):
                if line not in notes:
                    notes.append(line)
                    if b.get('zh') and b['zh'] != b['en'] and not b['zh'].startswith('[ERROR') and b['zh'] not in zh_notes:
                        zh_notes.append(b['zh'])
                continue

            has_affil = bool(AFFILIATION_REGEX.search(line))
            is_pure_affil = bool(re.match(r'^\s*(?:\$\^?\{[0-9*†‡,]+\}\$|\^[0-9*†‡,]+|[0-9*†‡§]+\s+)', line)) and has_affil

            if is_pure_affil or (has_affil and len(AFFILIATION_REGEX.findall(line)) >= 2):
                parts = re.split(r'(?:\$\^?\{[0-9*†‡,]+\}\$|\^[0-9*†‡,]+|[;]+|\s{2,})', line)
                for part in parts:
                    p = re.sub(r'^[0-9*†‡§,\s]+|[,\s]+$', '', part).strip()
                    if p and len(p) > 3 and p.lower() not in seen_affils and AFFILIATION_REGEX.search(p):
                        add_affil(p, b.get('zh'))
                continue

            if has_affil:
                m = AFFILIATION_REGEX.search(line)
                if m and m.start() > 3 and ',' not in line[:m.start()]:
                    add_author(line[:m.start()].strip())
                    add_affil(line[m.start():].strip(), b.get('zh'))
                    continue
                else:
                    add_affil(line, b.get('zh'))
                    continue

            # Split authors by comma (not inside braces)
            parts = re.split(r',\s*(?![^{}]*\})|\s+and\s+', line)
            for part in parts:
                add_author(part)

    return {
        'authors': authors, 'affiliations': affiliations, 'emails': emails,
        'urls': urls, 'notes': notes, 'unclassified': unclassified,
        'zh_affiliations': zh_affiliations, 'zh_notes': zh_notes,
    }


def is_code_caption_text(text: str) -> bool:
    if not text:
        return False
    t = text.strip()
    if len(t) > 160:
        return False
    return bool(
        re.match(r'^\s*\([a-z0-9]+\)\s*(?:[A-Za-z0-9_-]+\s+)?(?:pseudo\s*code|code|algorithm|implementation)', t, re.I) or
        re.match(r'^\s*(?:Listing|Algorithm)\s+\d+[a-z]?\s*[:\.]', t, re.I) or
        re.match(r'^\s*(?:Sampled\s+API\s+List|Prompt\s+Template)\b', t, re.I)
    )


def is_code_start_text(text: str) -> bool:
    if not text:
        return False
    t = text.strip()
    return bool(
        re.search(r'^\s*(?:def\s+[a-zA-Z0-9_]|class\s+[a-zA-Z0-9_]|Algorithm\s+\d|Listing\s+\d|function\s+[a-zA-Z0-9_]|procedure\s+[a-zA-Z0-9_])', t, re.I | re.M) or
        re.search(r'^\s*(?:system_prompt|user_prompt|diversity_user_prompt|Finish_function_description)\s*:', t, re.I) or
        re.match(r'^\s*(?:\[\s*\{|\{\s*"name"|\{\s*"Query")', t)
    )


def clean_code_block_text(code: str) -> str:
    if not code:
        return ''
    c = code.replace('\r\n', '\n')
    c = re.sub(r'\n\s*→\s*', ' ', c)
    c = c.replace('→', '->')
    c = re.sub(r'\\dots\b', '...', c)
    c = re.sub(r'\b([a-zA-Z0-9_]+)\s*\.\s+([a-zA-Z0-9_]+)\b', r'\1.\2', c)
    c = re.sub(r'\.\s+([a-zA-Z0-9_]+)', r'.\1', c)
    return c


def generate_bilingual_markdown(task) -> str:
    from infer.ovis_parser import clean_latex_math
    from infer.translate_v2 import is_code_block_text

    blocks = getattr(task, "blocks", []) or []
    tldr = getattr(task, "tldr", {}) or {}
    filename = getattr(task, "filename", "paper.pdf")

    md_lines = []

    # Identify page 1 primary title & author blocks
    first_title_idx = next((i for i, b in enumerate(blocks) if b.get('page') == 1 and b.get('type') == 'title'), -1)
    last_title_idx = first_title_idx
    if first_title_idx != -1:
        while (last_title_idx + 1 < len(blocks) and
               blocks[last_title_idx + 1].get('page') == 1 and
               blocks[last_title_idx + 1].get('type') == 'title'):
            nxt = (blocks[last_title_idx + 1].get('en') or '').strip().lower()
            if nxt.startswith('abstract') or nxt.startswith('摘要'):
                break
            last_title_idx += 1

    candidate_author_blocks = []
    author_end_idx = -1
    if first_title_idx != -1:
        for i in range(last_title_idx + 1, len(blocks)):
            b = blocks[i]
            if b.get('page') != 1:
                break
            en_lower = (b.get('en') or '').strip().lower()
            is_table_grid = b.get('type') == 'table' and (EMAIL_REGEX.search(b.get('en', '')) or AFFILIATION_REGEX.search(b.get('en', '')))
            if is_table_grid:
                candidate_author_blocks.append(b)
                continue
            is_author_or_affil = (
                len((b.get('en') or '').split(',')) >= 3 or
                bool(re.search(r'\$\^?\{?[*†‡0-9a-z,\s]+\}?\s*\$', b.get('en', ''))) or
                bool(AFFILIATION_REGEX.search(b.get('en', ''))) or
                bool(EMAIL_REGEX.search(b.get('en', ''))) or
                bool(NOTE_REGEX.search(en_lower)) or
                bool(re.search(r'\b(?:correspondence|equal contribution|university|institute|laboratory|department|school)\b', en_lower))
            )
            is_stop = (
                b.get('type') == 'header' or
                (b.get('type') == 'title' and not en_lower.startswith('author')) or
                en_lower.startswith('abstract') or
                en_lower.startswith('摘要') or
                re.match(r'^(?:(?:\d+\.?|[I|V|X]+\.?)\s+)?(?:introduction|overview)', en_lower) or
                b.get('type') in ('equation', 'table', 'image', 'chart', 'figure') or
                (not is_author_or_affil and len(b.get('en', '')) > 280)
            )
            if is_stop:
                author_end_idx = i
                break
            if b.get('type') == 'aside_text' and 'arxiv' in en_lower:
                continue
            candidate_author_blocks.append(b)

    should_group_authors = (
        len(candidate_author_blocks) > 0 and
        (len(candidate_author_blocks) >= 2 or
         EMAIL_REGEX.search(candidate_author_blocks[0].get('en', '')) or
         AFFILIATION_REGEX.search(candidate_author_blocks[0].get('en', '')) or
         '*' in (candidate_author_blocks[0].get('en') or '') or
         '$' in (candidate_author_blocks[0].get('en') or ''))
    )

    # 1. Primary Title
    if first_title_idx != -1:
        t_en = blocks[first_title_idx].get('en', '').strip()
        t_zh = blocks[first_title_idx].get('zh', '').strip()
        md_lines.append(f"# {t_en}\n")
        if t_zh and t_zh != t_en and not t_zh.startswith('[ERROR'):
            md_lines.append(f"# {t_zh}\n")
    else:
        md_lines.append(f"# {filename}\n")

    # 2. Author metadata
    if should_group_authors:
        meta = _parse_author_metadata(candidate_author_blocks, all_blocks=blocks)
        if meta['authors']:
            auth_str = ", ".join([
                (a['name'] + (f" ({''.join(a['markers'])})" if a['markers'] else ""))
                for a in meta['authors']
            ])
            md_lines.append(f"**作者 / Authors**: {auth_str}\n")
        if meta['affiliations']:
            aff_str = " | ".join(meta['affiliations'])
            md_lines.append(f"**单位 / Affiliations**: {aff_str}\n")
        if meta['zh_affiliations']:
            zh_aff_str = " | ".join(meta['zh_affiliations'])
            md_lines.append(f"**中文机构**: {zh_aff_str}\n")
        if meta['emails']:
            md_lines.append(f"**联系方式 / Contacts**: {', '.join(meta['emails'])}\n")
        if meta['urls']:
            md_lines.append(f"**代码与链接 / Links**: {', '.join(meta['urls'])}\n")
        if meta['notes']:
            for note in meta['notes']:
                md_lines.append(f"> *{note}*\n")
        if meta['zh_notes']:
            for zn in meta['zh_notes']:
                md_lines.append(f"> *{zn}*\n")
        md_lines.append("\n")

    # 3. Paper TL;DR
    if tldr and any(tldr.values()):
        md_lines.append("> ## 论文速读 (Paper TL;DR)\n>")
        if tldr.get('background'):
            md_lines.append(f"> - **研究背景与核心痛点**: {tldr['background']}\n>")
        if tldr.get('method'):
            md_lines.append(f"> - **核心创新与方法方案**: {tldr['method']}\n>")
        if tldr.get('metrics'):
            md_lines.append(f"> - **实验性能与关键指标**: {tldr['metrics']}\n>")
        if tldr.get('conclusion'):
            md_lines.append(f"> - **工作价值与学术结论**: {tldr['conclusion']}\n>")
        md_lines.append("\n")

    skip_until_idx = (author_end_idx - 1) if (should_group_authors and author_end_idx != -1) else (
        (last_title_idx + len(candidate_author_blocks)) if should_group_authors else -1
    )

    last_page = 0
    i = 0
    n = len(blocks)
    while i < n:
        if i <= skip_until_idx:
            i += 1
            continue

        b = blocks[i]
        page = b.get('page', 1)
        if page != last_page:
            md_lines.append(f"\n---\n<!-- 第 {page} 页 / Page {page} -->\n")
            last_page = page

        # Skip primary title on page 1 as it was rendered above
        if i == first_title_idx:
            i += 1
            continue

        # Code cluster check
        is_cap = is_code_caption_text(b.get('en', ''))
        next_is_code = (i + 1 < n and blocks[i+1].get('page') == page and
                        (is_code_block_text(blocks[i+1].get('en', '')) or blocks[i+1].get('type') == 'algorithm'))
        is_code = is_code_block_text(b.get('en', '')) or b.get('type') == 'algorithm'

        if is_code or (is_cap and next_is_code):
            j = i
            cluster = []
            while j < n and blocks[j].get('page') == page:
                cur = blocks[j]
                cur_is_code = is_code_block_text(cur.get('en', '')) or cur.get('type') == 'algorithm'
                cur_is_cap = is_code_caption_text(cur.get('en', ''))
                has_code_or_cap = any(
                    blocks[k].get('page') == page and
                    (is_code_block_text(blocks[k].get('en', '')) or is_code_caption_text(blocks[k].get('en', '')))
                    for k in range(j + 1, n)
                )
                cur_is_comment = (len(cur.get('en', '')) < 120 and has_code_or_cap and
                                  not bool(re.match(r'^\d+\.?\d*\s+[A-Z]', cur.get('en', '').strip())))
                if cur_is_code or cur_is_cap or cur_is_comment:
                    cluster.append(cur)
                    j += 1
                else:
                    break

            code_and_comments = [c for c in cluster if not is_code_caption_text(c.get('en', ''))]
            caption_blocks = [c for c in cluster if is_code_caption_text(c.get('en', ''))]

            if code_and_comments:
                snippets = []
                cur_sn = []
                for item in code_and_comments:
                    if cur_sn and is_code_start_text(item.get('en', '')):
                        snippets.append(cur_sn)
                        cur_sn = [item]
                    else:
                        cur_sn.append(item)
                if cur_sn:
                    snippets.append(cur_sn)

                for sn_idx, sn in enumerate(snippets):
                    full_code = []
                    for item in sn:
                        en_text = item.get('en', '').strip()
                        if not is_code_block_text(en_text) and not en_text.startswith('#'):
                            full_code.append('# ' + en_text)
                        else:
                            full_code.append(en_text)
                    clean_full = clean_code_block_text('\n'.join(full_code))
                    matched_cap = caption_blocks[sn_idx] if sn_idx < len(caption_blocks) else (
                        caption_blocks[0] if caption_blocks else None
                    )

                    md_lines.append(f"```python\n{clean_full}\n```\n")
                    if matched_cap:
                        cap_en = matched_cap.get('en', '').strip()
                        cap_zh = matched_cap.get('zh', '').strip()
                        md_lines.append(f"*{cap_en}*  ")
                        if cap_zh and cap_zh != cap_en and not cap_zh.startswith('[ERROR'):
                            md_lines.append(f"*{cap_zh}*\n")
                        else:
                            md_lines.append("\n")
                i = j
                continue

        # Image / Chart / Figure
        btype = b.get('type')
        if btype in ('image', 'chart', 'figure'):
            fid = b.get('figure_id')
            cap_en = ''
            cap_zh = ''
            if i + 1 < n and blocks[i+1].get('type') in ('image_caption', 'image_footnote'):
                cap_en = blocks[i+1].get('en', '').strip()
                cap_zh = blocks[i+1].get('zh', '').strip()
                i += 1
            if fid:
                md_lines.append(f"![{cap_en or 'Figure'}](figures/{fid})\n")
            if cap_en:
                md_lines.append(f"*{cap_en}*  ")
                if cap_zh and cap_zh != cap_en and not cap_zh.startswith('[ERROR'):
                    md_lines.append(f"*{cap_zh}*\n")
                else:
                    md_lines.append("\n")
            i += 1
            continue

        # Equation
        if btype == 'equation':
            raw = b.get('en', '').strip()
            clean = clean_latex_math(raw)
            if clean.startswith('$$') and clean.endswith('$$'):
                clean = clean[2:-2].strip()
            elif clean.startswith(r'\[') and clean.endswith(r'\]'):
                clean = clean[2:-2].strip()
            md_lines.append(f"$$\n{clean}\n$$\n")
            i += 1
            continue

        # Title / Header
        if btype == 'title':
            en = b.get('en', '').strip()
            zh = b.get('zh', '').strip()
            md_lines.append(f"## {en}\n")
            if zh and zh != en and not zh.startswith('[ERROR'):
                md_lines.append(f"### {zh}\n")
            i += 1
            continue

        # Table
        if btype == 'table':
            raw = b.get('en', '').strip()
            zh = b.get('zh', '').strip()
            md_lines.append(f"{raw}\n")
            if zh and zh != raw and not zh.startswith('[ERROR'):
                md_lines.append(f"{zh}\n")
            i += 1
            continue

        # Passthrough & normal text
        en = b.get('en', '').strip()
        zh = b.get('zh', '').strip()
        if en:
            md_lines.append(f"{en}\n")
            if zh and zh != en and not zh.startswith('[ERROR') and not b.get('passthrough'):
                md_lines.append(f"{zh}\n")
        i += 1

    return '\n'.join(md_lines)


@router.get("/download/{task_id}")
async def download_result(task_id: str):
    """Download ZIP archive containing bilingual Markdown and extracted figure images."""
    task = task_manager.get(task_id)
    if not task or not getattr(task, 'blocks', None):
        task = task_manager.load_task_blocks(task_id) or task
    if not task:
        raise HTTPException(404, "Task not found")
    if task.status != "completed":
        raise HTTPException(400, "Translation not completed yet")

    _ensure_task_tldr(task)

    # 1. Generate bilingual Markdown
    markdown_content = generate_bilingual_markdown(task)

    # 2. Collect figure images
    figures_to_include = {}
    for fig_path in getattr(task, 'figures', []):
        if fig_path and os.path.isfile(fig_path):
            figures_to_include[os.path.basename(fig_path)] = fig_path

    from backend.task_manager import _task_dir
    hist_fig_dir = os.path.join(_task_dir(task_id), "figures")
    if os.path.isdir(hist_fig_dir):
        for fname in os.listdir(hist_fig_dir):
            full_p = os.path.join(hist_fig_dir, fname)
            if os.path.isfile(full_p) and fname not in figures_to_include:
                figures_to_include[fname] = full_p

    temp_fig_dir = os.path.join(tempfile.gettempdir(), f"ppt_{task_id}_figures")
    if os.path.isdir(temp_fig_dir):
        for fname in os.listdir(temp_fig_dir):
            full_p = os.path.join(temp_fig_dir, fname)
            if os.path.isfile(full_p) and fname not in figures_to_include:
                figures_to_include[fname] = full_p

    # 3. Create in-memory ZIP archive
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w', compression=zipfile.ZIP_DEFLATED) as zf:
        base_name = os.path.splitext(task.filename)[0]
        safe_base = re.sub(r'[\\/*?:"<>|]', '_', base_name).strip() or "paper"
        md_filename = f"{safe_base}_bilingual.md"

        # Write Markdown file at root of zip
        zf.writestr(md_filename, markdown_content.encode('utf-8'))

        # Write figures into figures/ subfolder in zip
        for fname, fpath in figures_to_include.items():
            try:
                with open(fpath, "rb") as img_f:
                    zf.writestr(f"figures/{fname}", img_f.read())
            except Exception as e:
                print(f"Warning: Failed to add figure {fname} to zip: {e}")

    zip_buffer.seek(0)
    zip_filename = f"{safe_base}_bilingual.zip"
    encoded_name = quote(zip_filename, safe='')
    return StreamingResponse(
        zip_buffer,
        media_type="application/zip",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{encoded_name}",
            "Content-Type": "application/zip",
        }
    )


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
    tldr = _ensure_task_tldr(task)
    result = task.to_dict()
    result["blocks"] = task.blocks
    result["tldr"] = tldr
    result["figures"] = [os.path.basename(f) for f in task.figures]
    return result


@router.get("/task/{task_id}/tldr")
@router.get("/history/{task_id}/tldr")
async def get_task_tldr(task_id: str):
    """Retrieve structured Paper TL;DR for a task."""
    task = task_manager.get(task_id) or task_manager.load_task_blocks(task_id)
    if not task:
        raise HTTPException(404, "Task not found")
    tldr = _ensure_task_tldr(task)
    return {"task_id": task_id, "tldr": tldr}


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
    pdf_target = task.pdf_path if task and task.pdf_path and os.path.isfile(task.pdf_path) else None
    if not pdf_target:
        from backend.task_manager import _task_dir
        hist_pdf = os.path.join(_task_dir(task_id), "document.pdf")
        upload_pdf = os.path.join(UPLOAD_DIR, f"{task_id}.pdf")
        if os.path.isfile(hist_pdf):
            pdf_target = hist_pdf
            if task: task.pdf_path = hist_pdf
        elif os.path.isfile(upload_pdf):
            pdf_target = upload_pdf
            if task: task.pdf_path = upload_pdf
        else:
            raise HTTPException(404, "Page image not available")

    import fitz
    os.makedirs(page_dir, exist_ok=True)
    doc = fitz.open(pdf_target)
    try:
        idx = page_num - 1
        if idx < 0 or idx >= len(doc):
            raise HTTPException(404, "Page out of range")
        pix = doc[idx].get_pixmap(dpi=dpi)
        pix.save(page_path)
    finally:
        doc.close()
    return FileResponse(page_path, media_type="image/png")
