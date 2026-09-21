"""
Translation worker — two-phase batch: OCR all pages → translate all blocks.
Phase 1: Load OCR model once, recognize all pages, store blocks in memory.
Phase 2: Load translation model, extract direction, translate blocks in order.
"""
import os, sys, time, threading, tempfile, re
from queue import Queue

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from backend.task_manager import task_manager

from typing import Optional, Any

_event_queues: dict[str, Queue] = {}

def get_event_queue(task_id: str) -> Queue:
    if task_id not in _event_queues:
        _event_queues[task_id] = Queue()
    return _event_queues[task_id]

def remove_event_queue(task_id: str):
    _event_queues.pop(task_id, None)

def _emit(task_id: str, event: dict):
    q = _event_queues.get(task_id)
    if q: q.put(event)


def run_translation(task, dpi: int, cancel_event: threading.Event,
                    start_page: int = 0, end_page: Optional[int] = None,
                    gpu_lock: Any = None, ocr_engine_type: Optional[str] = None):
    task_id = task.task_id
    from config import model_path, get, get_ocr_engine_config

    if gpu_lock is not None and not gpu_lock.locked():
        gpu_lock.acquire()

    ocr_cfg = get_ocr_engine_config(ocr_engine_type)
    selected_engine_id = ocr_cfg.get('id', 'unlimited')
    task_manager.update(task_id, ocr_model=selected_engine_id)

    trans_model = model_path('translation')

    ocr = None
    translator = None
    doc = None
    img_paths = []

    try:
        import fitz
        from infer.ocr import OCREngineFactory
        from infer.translate_v2 import SmartTranslator, merge_split_blocks, find_cross_page_pairs, split_translation, is_pseudo_title, is_code_block_text

        doc = fitz.open(task.pdf_path)
        doc_len = len(doc)
        s_page = max(0, start_page or 0)
        e_page = min(doc_len, end_page) if end_page is not None else min(doc_len, task.page_count)
        total_pages = max(0, e_page - s_page)
        _emit(task_id, {"type": "start", "total_pages": total_pages, "ocr_model": selected_engine_id})

        # 统一语义类型定义
        TEXT_TYPES = {
            'text',                              # 正文
            'image_caption',                     # 图注
            'image_footnote',                    # 图片脚注
        }
        PASSTHROUGH = {
            'title',                             # 标题，不翻译（用户非协商硬性要求）
            'ref_text',                          # 参考文献，保留原文
            'equation', 'table',                 # 公式、表格
            'aside_text', 'header', 'footer',    # 边注、页眉、页脚
            'algorithm',                         # 算法块
        }
        HIDE_TYPES = {'page_number', 'page_footnote'}  # 页码、页脚注释
        IMAGE_TYPES = {'image', 'chart'}         # 图片/图表，裁剪特殊处理
        ALL_KNOWN_TYPES = TEXT_TYPES | PASSTHROUGH | HIDE_TYPES | IMAGE_TYPES

        # ════════════════════════════════════════════════════════
        #  Phase 1: OCR 全量识别（模型加载一次，逐页扫描）
        # ════════════════════════════════════════════════════════
        _emit(task_id, {"type": "phase", "phase": "ocr", "ocr_model": selected_engine_id})
        print(f"[Phase 1] OCR [{selected_engine_id}]: {total_pages} pages (pages {s_page+1} to {e_page})")

        all_page_blocks = []  # list of list[dict], one per page

        try:
            ocr = OCREngineFactory.create_engine(
                engine_type=selected_engine_id,
                model_path=ocr_cfg.get('model_path'),
                mmproj_path=ocr_cfg.get('mmproj_path'),
                n_gpu_layers=get('gpu', 'ocr_layers', default=99),
                n_ctx=get('ocr', 'n_ctx', default=8192),
                flash_attn=get('ocr', 'flash_attn', default=True))

            # 异步双缓冲流水线：GPU 进行当前页 OCR 时，后台独立线程全重叠预渲染下一页
            ocr_stream = ocr.recognize_pdf_stream(
                doc,
                page_range=range(s_page, e_page),
                dpi=dpi,
                max_tokens=get('ocr', 'max_tokens', default=4096),
                cancel_event=cancel_event,
                penalty_last_n=get('ocr', 'penalty_last_n', default=256),
                penalty_repeat=get('ocr', 'penalty_repeat', default=1.20),
                penalty_freq=get('ocr', 'penalty_freq', default=0.20),
                penalty_present=get('ocr', 'penalty_present', default=0.05),
                fast_greedy=get('ocr', 'fast_greedy', default=True),
            )

            for page_num, ocr_text, raw_page_text, img_path, pw, ph in ocr_stream:
                if cancel_event.is_set(): raise InterruptedError("Cancelled")
                img_paths.append(img_path)

                blocks = ocr.parse_output(ocr_text)
                if selected_engine_id == 'unlimited':
                    blocks = merge_split_blocks(blocks)

                # ── 深度五层 OCR 优化管线 ──
                # 1. 块内死循环截断 + 多周期交替循环检测 + 纯净指纹/子串去重 + 空间 IoU 重叠过滤
                blocks = deduplicate_page_blocks(blocks)

                # 2. 断词断句修复（学术连字符智能缝合，如 trans-\n duction -> transduction）
                for b in blocks:
                    if 'text' in b and b['text']:
                        b['text'] = dehyphenate_text(b['text'])

                # 3. 学术版面自适应与双栏阅读顺序排列（Unlimited-OCR 需要重排，Ovis 原生自然语序跳过）
                if selected_engine_id == 'unlimited' or ocr_cfg.get('reading_order_sorted', False):
                    blocks = sort_reading_order(blocks)

                # 分类 + 裁剪
                page_blocks = []
                for i, b in enumerate(blocks):
                    bt = b['type']
                    if bt in HIDE_TYPES:
                        continue
                    if bt not in ALL_KNOWN_TYPES:
                        en = _fix_latex(b['text'])
                        page_blocks.append({
                            'page': page_num+1, 'idx': i, 'type': bt,
                            'en': en, 'zh': en,
                            'passthrough': True, 'bbox': b.get('bbox', []),
                        })
                        continue
                    if bt in TEXT_TYPES or bt in PASSTHROUGH:
                        # 首页作者、机构、邮箱、版权等元数据自动标记为 passthrough 保留原文，防止误译为人名幻觉
                        is_front_matter = is_front_matter_metadata(b['text'], page_num)
                        is_code = is_code_block_text(b['text'])
                        if is_code and bt in TEXT_TYPES:
                            bt = 'algorithm'
                        is_pt = (bt in PASSTHROUGH) or is_front_matter or is_code or b.get('passthrough', False)
                        en = _fix_latex(b['text'])
                        page_blocks.append({
                            'page': page_num+1, 'idx': i, 'type': bt,
                            'en': en, 'zh': en if is_pt else '',
                            'passthrough': is_pt, 'bbox': b.get('bbox', []),
                        })
                    elif bt in IMAGE_TYPES and b.get('bbox'):
                        try:
                            fig_idx = len(task.figures)
                            fp = _crop(img_path, b['bbox'], pw, ph, task_id, page_num, fig_idx)
                            task.figures.append(fp)
                            fid = f"p{page_num}_f{fig_idx}.png"
                            page_blocks.append({
                                'page': page_num+1, 'idx': i, 'type': bt,
                                'en': '', 'zh': '', 'passthrough': True, 'figure_id': fid, 'bbox': b['bbox'],
                            })
                            _emit(task_id, {"type":"figure","page":page_num+1,"idx":i,"figure_id":fid,"bbox":b['bbox']})
                        except Exception as e:
                            print(f"  crop failed: {e}")

                page_blocks = _merge_eq_single(page_blocks)

                # 4. 双通道交叉质检（PyMuPDF 原生真实字符 vs OCR 识别字符）
                raw_clean_chars = len(re.sub(r'\s+', '', raw_page_text))
                ocr_clean_chars = sum(len(re.sub(r'\s+', '', b.get('en', '')))
                                      for b in page_blocks if b.get('type') in TEXT_TYPES | {'title', 'ref_text'})
                if raw_clean_chars > 150:
                    coverage_ratio = ocr_clean_chars / raw_clean_chars
                    if coverage_ratio < 0.45:
                        print(f"  [Dual-Channel Alert] Page {page_num+1}: OCR coverage only {coverage_ratio:.1%} ({ocr_clean_chars}/{raw_clean_chars} chars). Potential bottom omission!")
                    elif coverage_ratio > 2.0:
                        print(f"  [Dual-Channel Alert] Page {page_num+1}: OCR ratio {coverage_ratio:.1%} ({ocr_clean_chars}/{raw_clean_chars} chars). Potential repetition loop!")

                all_page_blocks.append(page_blocks)

                # 发送该页已识别出的结构和文本供前端即时预览
                _emit(task_id, {
                    "type": "ocr_page_blocks",
                    "page": page_num + 1,
                    "blocks": [
                        {
                            "page": b['page'],
                            "idx": b['idx'],
                            "type": b['type'],
                            "en": b['en'],
                            "zh": b.get('zh', ''),
                            "figure_id": b.get('figure_id', ''),
                            "bbox": b.get('bbox', []),
                            "passthrough": b.get('passthrough', False),
                        }
                        for b in page_blocks
                    ]
                })

                _emit(task_id, {"type": "ocr_progress",
                                "page": page_num - s_page + 1, "total_pages": total_pages})
                print(f"  OCR page {page_num+1}/{e_page}: {len(page_blocks)} blocks")

        finally:
            if ocr:
                ocr.close()
                ocr = None
            if doc:
                doc.close()
                doc = None

        # 清理临时图片
        for p in img_paths:
            try: os.unlink(p)
            except OSError: pass

        # 跨页段落检测（找出跨页延续的 text block 对，翻译时合并、翻译后拆分）
        cross_page_pairs = find_cross_page_pairs(all_page_blocks)
        cross_page_map = {}  # id(block_a) -> (block_a, block_b)
        for ba, bb in cross_page_pairs:
            cross_page_map[id(ba)] = (ba, bb)

        total_blocks = sum(len(pb) for pb in all_page_blocks)
        print(f"[Phase 1] Done: {total_blocks} blocks across {total_pages} pages")

        # ════════════════════════════════════════════════════════
        #  Phase 2: 全量翻译（加载翻译模型，逐 block 处理）
        # ════════════════════════════════════════════════════════
        _emit(task_id, {"type": "phase", "phase": "translate",
                         "total_blocks": total_blocks})
        print(f"[Phase 2] Translate: {total_blocks} blocks")

        try:
            translator = SmartTranslator(
                model_path=trans_model,
                n_gpu_layers=get('gpu', 'trans_layers', default=99),
                verify=get('translation', 'verify', default=True))

            # 从第 0 页提取论文方向（排除 passthrough 首页元数据）
            abstract_block = None
            if all_page_blocks:
                first_page_text = [b for b in all_page_blocks[0]
                                   if b['type'] == 'text' and not b.get('passthrough') and not is_pseudo_title(b['en'], b['type'])]
                if first_page_text:
                    abstract_block = max(first_page_text, key=lambda b: len(b['en']))
                    translator.set_direction_from_abstract(abstract_block['en'])

            consumed_blocks = set()
            for ba, bb in cross_page_pairs:
                consumed_blocks.add(id(bb))

            block_idx = 0
            for page_blocks in all_page_blocks:
                page_num = page_blocks[0]['page'] if page_blocks else 0
                _emit(task_id, {"type": "page_start", "page": page_num})

                for b in page_blocks:
                    if cancel_event.is_set(): raise InterruptedError("Cancelled")

                    # 如果这个 block 已经被跨页合并处理过，现在正是它所属的页面，发射它！
                    if id(b) in consumed_blocks:
                        block_idx += 1
                        _emit(task_id, {"type":"block_done","page":b['page'],"idx":b['idx'],
                                        "block_type":b['type'],"en":b['en'],"zh":b.get('zh', ''),"verified":True})
                        _emit(task_id, {"type": "translate_progress",
                                        "done": block_idx, "total": total_blocks})
                        continue

                    if b.get('passthrough'):
                        _emit(task_id, {"type":"block_done","page":b['page'],"idx":b['idx'],
                                        "block_type":b['type'],"en":b['en'],"zh":b['zh'],
                                        "verified":True,"figure_id":b.get('figure_id','')})
                    else:
                        text = b['en']
                        btype = b['type']

                        # 跨页合并翻译：合并翻译，但此时仅发射 block_a
                        if id(b) in cross_page_map:
                            ba, bb = cross_page_map[id(b)]
                            combined_en = ba['en'].rstrip() + ' ' + bb['en'].lstrip()
                            try:
                                combined_zh = translator.translate_block(combined_en, btype)
                            except Exception as e:
                                combined_zh = f"[ERROR: {e}]"
                            if combined_zh is None:
                                combined_zh = combined_en

                            zh1, zh2 = split_translation(
                                combined_en, combined_zh, len(ba['en']), len(bb['en']))
                            ba['zh'] = zh1
                            bb['zh'] = zh2

                            # 仅发射 block_a（当前页），block_b 留到下一页实际遍历时发射
                            _emit(task_id, {"type":"block_done","page":ba['page'],"idx":ba['idx'],
                                            "block_type":ba['type'],"en":ba['en'],"zh":zh1,"verified":True})
                        else:
                            try:
                                zh = translator.translate_block(text, btype)
                            except Exception as e:
                                zh = f"[ERROR: {e}]"

                            if zh is None:
                                zh = text
                            b['zh'] = zh

                            _emit(task_id, {"type":"block_done","page":b['page'],"idx":b['idx'],
                                            "block_type":btype,"en":text,"zh":zh,"verified":True})

                    block_idx += 1
                    _emit(task_id, {"type": "translate_progress",
                                    "done": block_idx, "total": total_blocks})

                _emit(task_id, {"type": "page_done", "page": page_num, "blocks": len(page_blocks)})
                task.blocks.extend(page_blocks)

            print(f"  Translation stats: {translator.stats}")
            total_cnt = max(translator.stats['total'], 1)
            passed_cnt = translator.stats['passed'] + translator.stats['retried']
            pass_rate_val = (passed_cnt / total_cnt) * 100
            task.quality = {
                "total_blocks": total_blocks,
                "pass_rate": f"{pass_rate_val:.1f}%",
                "passed": translator.stats['passed'],
                "retried": translator.stats['retried'],
                "failed": translator.stats['failed'],
                "skipped": translator.stats['skipped'],
            }
            # 提炼论文四维核心导读 (Paper TL;DR)
            tldr = {}
            if abstract_block and abstract_block.get('zh'):
                try:
                    tldr = translator.generate_paper_tldr(abstract_block['zh'])
                except Exception as e:
                    print(f"  [Worker] LLM TL;DR generation failed: {e}")
            if not tldr or not any(tldr.values()):
                try:
                    from backend.tldr_extractor import extract_paper_tldr_from_blocks
                    all_blocks_flat = [b for pb in all_page_blocks for b in pb]
                    tldr = extract_paper_tldr_from_blocks(all_blocks_flat)
                except Exception as e:
                    print(f"  [Worker] Structural TL;DR extraction failed: {e}")

            if tldr and any(tldr.values()):
                task.tldr = tldr
                _emit(task_id, {"type": "tldr", "tldr": tldr})

            _emit(task_id, {"type": "complete", "quality": task.quality})
            task_manager.update(task_id, status="completed", quality=task.quality, tldr=tldr)
            task_manager.save_task(task_id)

        finally:
            if translator:
                translator.close()
                translator = None

    except InterruptedError:
        task_manager.update(task_id, status="failed", error="Cancelled")
    except Exception as e:
        import traceback; traceback.print_exc()
        task_manager.update(task_id, status="failed", error=str(e))
    finally:
        if ocr:
            try: ocr.close()
            except Exception: pass
        if translator:
            try: translator.close()
            except Exception: pass
        if doc:
            try: doc.close()
            except Exception: pass
        for p in img_paths:
            try: os.unlink(p)
            except OSError: pass
        remove_event_queue(task_id)
        if gpu_lock is not None and gpu_lock.locked():
            try:
                gpu_lock.release()
            except RuntimeError:
                pass


# ── Helpers ──

def _bbox_iou(box1: list, box2: list) -> float:
    """Compute Intersection-over-Union (IoU) of two bounding boxes in [x1, y1, x2, y2]."""
    if not box1 or not box2 or len(box1) < 4 or len(box2) < 4:
        return 0.0
    ix1 = max(box1[0], box2[0])
    iy1 = max(box1[1], box2[1])
    ix2 = min(box1[2], box2[2])
    iy2 = min(box1[3], box2[3])
    if ix2 <= ix1 or iy2 <= iy1:
        return 0.0
    inter_area = (ix2 - ix1) * (iy2 - iy1)
    area1 = max(0, box1[2] - box1[0]) * max(0, box1[3] - box1[1])
    area2 = max(0, box2[2] - box2[0]) * max(0, box2[3] - box2[1])
    union_area = area1 + area2 - inter_area
    return (inter_area / union_area) if union_area > 0 else 0.0


def _bbox_overlap_ratio(inner_box: list, outer_box: list) -> float:
    """Calculate how much of inner_box is covered by outer_box."""
    if not inner_box or not outer_box or len(inner_box) < 4 or len(outer_box) < 4:
        return 0.0
    ix1 = max(inner_box[0], outer_box[0])
    iy1 = max(inner_box[1], outer_box[1])
    ix2 = min(inner_box[2], outer_box[2])
    iy2 = min(inner_box[3], outer_box[3])
    if ix2 <= ix1 or iy2 <= iy1:
        return 0.0
    inter_area = (ix2 - ix1) * (iy2 - iy1)
    inner_area = max(1, (inner_box[2] - inner_box[0]) * (inner_box[3] - inner_box[1]))
    return inter_area / inner_area


def _text_fingerprint(text: str) -> str:
    """Normalize text into pure alphanumeric characters for robust duplicate detection."""
    return re.sub(r'[^a-zA-Z0-9]', '', text.lower())


def _text_token_jaccard(t1: str, t2: str) -> float:
    """Compute word-level Jaccard similarity between two texts."""
    tokens1 = set(re.findall(r'\b[a-zA-Z0-9]{2,}\b', t1.lower()))
    tokens2 = set(re.findall(r'\b[a-zA-Z0-9]{2,}\b', t2.lower()))
    if not tokens1 or not tokens2:
        return 0.0
    inter = len(tokens1 & tokens2)
    union = len(tokens1 | tokens2)
    return inter / union if union > 0 else 0.0


def truncate_repetition_loops(text: str) -> str:
    """
    Detect and truncate repeating phrase/sentence loops within a single block of text.
    Handles autoregressive hallucination loops (e.g. phrase repeated 2+ times).
    """
    if not text or len(text) < 40:
        return text

    # 1. Regex pattern for exact consecutive repeats (length 8-300 chars, repeated >= 2 times)
    pattern = re.compile(r'(.{8,300}?)(?:\s*\1){2,}', re.DOTALL)
    cleaned = pattern.sub(r'\1', text)

    # 2. Consecutive word repeat loops (e.g. word word word word)
    cleaned = re.sub(r'\b(\w+)(?:\s+\1){3,}\b', r'\1', cleaned)

    # 3. Sentence-level consecutive loop detector
    sentences = re.split(r'(?<=[.!?。！？\n])\s*', cleaned)
    if len(sentences) > 4:
        dedup_sents = []
        for s in sentences:
            s_clean = s.strip()
            if not s_clean:
                continue
            recent = [x.strip() for x in dedup_sents[-5:]]
            if recent.count(s_clean) >= 2:
                continue
            dedup_sents.append(s)
        cleaned = ' '.join(dedup_sents)

    return cleaned.strip()


def deduplicate_page_blocks(blocks: list) -> list:
    """
    Comprehensive multi-layer deduplication for a single page of OCR blocks:
    1. Truncate intra-block repetition loops.
    2. Filter invalid placeholder blocks.
    3. Detect & prune alternating cycles (A-B-A-B, A-B-C-A-B-C).
    4. Exact & fuzzy fingerprint deduplication (with math/spacing tolerance).
    5. Substring fragment containment filter.
    6. Spatial IoU overlap deduplication.
    """
    if not blocks:
        return []

    # 1. Truncate intra-block loops
    for b in blocks:
        if b.get('type') in {'image', 'chart'}:
            continue
        txt = b.get('text', '') or b.get('en', '')
        if txt:
            cleaned = truncate_repetition_loops(txt)
            if 'text' in b: b['text'] = cleaned
            if 'en' in b: b['en'] = cleaned

    # 2. Filter invalid placeholder blocks (ALWAYS preserve image/chart blocks)
    valid_blocks = []
    for b in blocks:
        b_type = b.get('type', '')
        if b_type in {'image', 'chart'}:
            valid_blocks.append(b)
            continue

        txt = (b.get('text', '') or b.get('en', '')).strip()
        low = txt.lower()
        if not txt:
            continue
        if low in {'[non-text]', '[non text]', '[none]', '[blank]'}:
            continue
        nontext_count = low.count('[non-text]') + low.count('[non text]')
        if nontext_count > 0 and (nontext_count * 10) / max(len(low), 1) > 0.5:
            continue
        valid_blocks.append(b)

    # 3. Detect and prune alternating cycles (e.g. A-B-A-B, A-B-C-A-B-C)
    sigs = []
    for b in valid_blocks:
        b_type = b.get('type', '')
        if b_type in {'image', 'chart'}:
            bbox_sig = '_'.join(str(x) for x in b.get('bbox', []))
            sigs.append((b_type, f"img_{bbox_sig}"))
        else:
            txt = b.get('text', '') or b.get('en', '')
            fp = _text_fingerprint(txt)[:30]
            sigs.append((b_type, fp))

    drop_indices = set()
    n = len(valid_blocks)
    for cycle_len in (2, 3, 4):
        for i in range(n - 2 * cycle_len + 1):
            if i in drop_indices:
                continue
            pattern = sigs[i:i + cycle_len]
            if any(not s[1] for s in pattern):
                continue
            k = i + cycle_len
            while k + cycle_len <= n and sigs[k:k + cycle_len] == pattern:
                for drop_i in range(k, k + cycle_len):
                    drop_indices.add(drop_i)
                k += cycle_len

    cycle_filtered = [b for i, b in enumerate(valid_blocks) if i not in drop_indices]

    # 4. Fingerprint & Fuzzy text deduplication + Substring containment
    final_blocks = []
    seen_fps = []  # list of (fp, block_type, index_in_final)
    seen_image_boxes = []

    for b in cycle_filtered:
        b_type = b.get('type', '')
        bbox = b.get('bbox', [])

        # Dedicated deduplication for image/chart blocks
        if b_type in {'image', 'chart'}:
            is_dup_img = False
            if bbox and len(bbox) == 4:
                for prev_box in seen_image_boxes:
                    if _bbox_iou(bbox, prev_box) > 0.70:
                        is_dup_img = True
                        break
            if not is_dup_img:
                if bbox and len(bbox) == 4:
                    seen_image_boxes.append(bbox)
                final_blocks.append(b)
            continue

        # Handling for text blocks
        txt = (b.get('text', '') or b.get('en', '')).strip()
        fp = _text_fingerprint(txt)
        is_dup = False

        # Short text handling (< 25 alphanumeric chars)
        if len(fp) < 25:
            if final_blocks:
                prev_b = final_blocks[-1]
                prev_txt = (prev_b.get('text', '') or prev_b.get('en', '')).strip()
                prev_fp = _text_fingerprint(prev_txt)
                if prev_b.get('type') == b_type and prev_fp == fp:
                    is_dup = True
        else:
            # Long text (paragraphs, titles, references)
            for prev_fp, prev_type, prev_idx in seen_fps:
                # A. Exact fingerprint match
                if fp == prev_fp:
                    is_dup = True
                    break
                # B. Substring containment (e.g. B14 is suffix of B8)
                if len(fp) > 35 and (fp in prev_fp or prev_fp in fp):
                    len_ratio = min(len(fp), len(prev_fp)) / max(len(fp), len(prev_fp))
                    if len_ratio > 0.65 or len(fp) > 60:
                        is_dup = True
                        break
                # C. High fuzzy Jaccard similarity (> 0.85)
                if len(fp) > 40:
                    prev_b = final_blocks[prev_idx]
                    prev_raw = prev_b.get('text', '') or prev_b.get('en', '')
                    jaccard = _text_token_jaccard(txt, prev_raw)
                    if jaccard > 0.85:
                        is_dup = True
                        break

        # 5. Spatial IoU overlap check against recent text blocks
        if not is_dup and bbox and len(bbox) == 4:
            for prev_b in final_blocks[-6:]:
                if prev_b.get('type') in {'image', 'chart'}:
                    continue
                prev_box = prev_b.get('bbox', [])
                if prev_box and len(prev_box) == 4:
                    iou = _bbox_iou(bbox, prev_box)
                    overlap = max(_bbox_overlap_ratio(bbox, prev_box), _bbox_overlap_ratio(prev_box, bbox))
                    if iou > 0.5 or overlap > 0.75:
                        prev_raw = prev_b.get('text', '') or prev_b.get('en', '')
                        jaccard = _text_token_jaccard(txt, prev_raw)
                        if jaccard > 0.4 or fp in _text_fingerprint(prev_raw):
                            is_dup = True
                            break

        if not is_dup:
            seen_fps.append((fp, b_type, len(final_blocks)))
            final_blocks.append(b)

    return final_blocks


def dehyphenate_text(text: str) -> str:
    """
    Merge words broken by hyphen at line breaks (e.g. 'trans-\nduction' -> 'transduction').
    Preserves deliberate compound hyphens like 'state-of-the-art' or prefixes 'multi-head'.
    """
    if not text or '-' not in text:
        return text

    KNOWN_PREFIXES = {
        'self', 'multi', 'cross', 'semi', 'non', 'pre', 'post', 'co', 're',
        'sub', 'meta', 'hyper', 'well', 'state', 'out', 'over', 'under', 'all'
    }

    def _replace_hyphen(m):
        w1 = m.group(1)
        w2 = m.group(2)
        if w1.lower() in KNOWN_PREFIXES:
            return f"{w1}-{w2}"
        return f"{w1}{w2}"

    return re.sub(r'\b([a-zA-Z]{2,})-\s*\n\s*([a-zA-Z]{2,})\b', _replace_hyphen, text)


def sort_reading_order(blocks: list) -> list:
    """
    Sort blocks into proper academic reading order:
    - Detects single-column vs two-column layouts.
    - In single-column: natural top-to-bottom y1 sorting.
    - In two-column:
      1. Top full-width headers (title, abstract, wide teaser figures/tables)
      2. Left column blocks (sorted top-to-bottom by y1)
      3. Mid-page full-width blocks
      4. Right column blocks (sorted top-to-bottom by y1)
      5. Bottom full-width footers (notes, page numbers)
    """
    if not blocks or len(blocks) <= 2:
        return blocks

    left_col = []
    right_col = []
    full_width = []

    for b in blocks:
        box = b.get('bbox', [])
        if not box or len(box) < 4:
            full_width.append(b)
            continue
        x1, y1, x2, y2 = box
        width = x2 - x1
        x_mid = (x1 + x2) / 2.0

        if width > 550 or (x1 < 350 and x2 > 650):
            full_width.append(b)
        elif x_mid < 500:
            left_col.append(b)
        else:
            right_col.append(b)

    is_two_column = len(left_col) >= 2 and len(right_col) >= 2

    if not is_two_column:
        return sorted(blocks, key=lambda b: (b.get('bbox', [0, 0, 0, 0])[1] if b.get('bbox') else 0))

    col_boxes = [b['bbox'] for b in left_col + right_col if b.get('bbox')]
    col_min_y = min(box[1] for box in col_boxes)
    col_max_y = max(box[3] for box in col_boxes)

    top_blocks = [b for b in full_width if b.get('bbox') and b['bbox'][3] <= col_min_y + 30]
    bottom_blocks = [b for b in full_width if b.get('bbox') and b['bbox'][1] >= col_max_y - 30]
    mid_blocks = [b for b in full_width if b not in top_blocks and b not in bottom_blocks]

    top_sorted = sorted(top_blocks, key=lambda b: b['bbox'][1])
    left_sorted = sorted(left_col, key=lambda b: b['bbox'][1])
    right_sorted = sorted(right_col, key=lambda b: b['bbox'][1])
    bottom_sorted = sorted(bottom_blocks, key=lambda b: b['bbox'][1])
    mid_sorted = sorted(mid_blocks, key=lambda b: b['bbox'][1])

    return top_sorted + left_sorted + mid_sorted + right_sorted + bottom_sorted


def is_front_matter_metadata(text: str, page_num: int) -> bool:
    """
    Detect academic front matter on Page 1 (authors, affiliations, emails, copyright notices,
    contribution footnotes, conference proceedings).
    Such blocks must be preserved in original form (passthrough) to prevent name hallucination.
    """
    import re
    if page_num != 0:
        return False
    t = text.strip()
    low = t.lower()

    # 1. Contains email address
    if re.search(r'[\w\.-]+@[\w\.-]+\.\w+', t):
        return True

    # 2. Contains copyright / permission boilerplate on front page
    if any(k in low for k in ['permission to reproduce', 'copyright', 'all rights reserved', 'arxiv:']):
        return True

    # 3. Contains conference / proceedings publication headers or footers
    conference_keywords = [
        'conference on', 'proceedings of', 'annual meeting of', 'symposium on',
        'nips', 'neurips', 'iclr', 'icml', 'cvpr', 'eccv', 'iccv', 'acl', 'emnlp', 'naacl',
        'ieee', 'acm', 'long beach', 'published as a conference paper'
    ]
    if any(k in low for k in conference_keywords):
        return True

    # 4. Contains author contribution notes (regardless of text length)
    contribution_keywords = [
        'equal contribution', 'listing order is random', 'corresponding author',
        'contributed equally', 'work performed while at', 'author contributions'
    ]
    if any(k in low for k in contribution_keywords):
        return True

    # 5. Contains academic affiliation keywords
    affiliation_keywords = [
        'university', 'institute', 'department', 'laboratory', 'laboratories',
        'google research', 'google brain', 'microsoft research', 'meta ai',
        'deepmind', 'faculty of', 'school of', 'college of', 'center for',
        'centre for', 'corp.', 'ltd.', 'gmbh', 'campus'
    ]
    if any(k in low for k in affiliation_keywords):
        return True

    # 6. Short author-line pattern with footnote markers: e.g. "Ashish Vaswani* ...", "Aidan N. Gomez * \dagger"
    if len(t) < 80 and any(m in t for m in ['*', '†', '‡', '^', '+', '$^{*}$', '$^{\\dagger}$', '$^{*} $', '$^{+}$']):
        return True

    return False


def _fix_latex(text: str) -> str:
    import re
    from infer.ovis_parser import clean_latex_math
    text = re.sub(r'\\\[', '$$', text)
    text = re.sub(r'\\\]', '$$', text)
    text = re.sub(r'\\\(', '$', text)
    text = re.sub(r'\\\)', '$', text)
    text = clean_latex_math(text)
    return text


def _merge_eq_single(blocks: list) -> list:
    """Merge orphaned $$ equation lines in a single page."""
    new = []; i = 0
    while i < len(blocks):
        b = blocks[i]
        if b['type'] == 'equation' and b['en'].strip() in ('$$','') and i+1 < len(blocks) and blocks[i+1]['type'] == 'equation':
            nb = blocks[i+1]
            if nb['en'].strip() not in ('$$',''):
                b = dict(b); b['en'] = '$$\n' + nb['en']; i += 1
        if new and new[-1]['type'] == 'equation' and new[-1]['en'].strip() in ('$$',''):
            new[-1]['en'] = new[-1]['en'] + '\n' + b['en']; i += 1; continue
        new.append(b); i += 1
    return new


def _crop(img_path: str, bbox: list, iw: int, ih: int, tid: str, pn: int, fi: int) -> str:
    from PIL import Image
    # 归一化比例：Unlimited-OCR 与 Ovis 均为 0-1000 空间
    norm_scale = 1000.0 if any(c > 0 and c <= 1000 for c in bbox) else 1024.0
    sx, sy = iw / norm_scale, ih / norm_scale
    x1, y1 = max(0, int(bbox[0] * sx)), max(0, int(bbox[1] * sy))
    x2, y2 = min(iw, int(bbox[2] * sx)), min(ih, int(bbox[3] * sy))
    if x2 <= x1 or y2 <= y1:
        raise ValueError(f"Invalid crop box: [{x1}, {y1}, {x2}, {y2}] from bbox {bbox}")
    img = Image.open(img_path)
    cropped = img.crop((x1, y1, x2, y2))
    d = os.path.join(tempfile.gettempdir(), f"ppt_{tid}_figures")
    os.makedirs(d, exist_ok=True)
    out = os.path.join(d, f"p{pn}_f{fi}.png")
    cropped.save(out)
    return out
