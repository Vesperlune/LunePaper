"""
Translation worker — two-phase batch: OCR all pages → translate all blocks.
Phase 1: Load OCR model once, recognize all pages, store blocks in memory.
Phase 2: Load translation model, extract direction, translate blocks in order.
"""
import os, sys, time, threading, tempfile
from queue import Queue

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from backend.task_manager import task_manager

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


def run_translation(task, dpi: int, cancel_event: threading.Event):
    task_id = task.task_id
    from config import model_path, get

    ocr_model = model_path('ocr')
    mmproj    = model_path('mmproj')
    trans_model = model_path('translation')

    try:
        import fitz
        from infer.ocr import OCREngine, parse_ocr_output
        from infer.translate_v2 import SmartTranslator, merge_split_blocks, find_cross_page_pairs, split_translation, is_pseudo_title

        doc = fitz.open(task.pdf_path)
        total_pages = min(len(doc), task.page_count)
        _emit(task_id, {"type": "start", "total_pages": total_pages})

        # Unlimited-OCR 实际输出类型（13 篇论文 252 页实测）
        TEXT_TYPES = {
            'text',                              # 正文
            'image_caption',                     # 图注
            'image_footnote',                    # 图片脚注
        }
        PASSTHROUGH = {
            'title',                             # 标题，不翻译
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
        _emit(task_id, {"type": "phase", "phase": "ocr"})
        print(f"[Phase 1] OCR: {total_pages} pages")

        ocr = OCREngine(
            model_path=ocr_model, mmproj_path=mmproj,
            n_gpu_layers=get('gpu', 'ocr_layers', default=99),
            n_ctx=get('ocr', 'n_ctx', default=4096))

        all_page_blocks = []  # list of list[dict], one per page
        img_paths = []        # temp image paths for cleanup

        for page_num in range(total_pages):
            if cancel_event.is_set(): raise InterruptedError("Cancelled")

            # 渲染页面为 PNG
            page = doc[page_num]
            pix = page.get_pixmap(dpi=dpi)
            img_path = os.path.join(tempfile.gettempdir(), f"ppt_{task_id}_p{page_num}.png")
            pix.save(img_path)
            img_paths.append(img_path)

            # OCR 推理
            ocr_text = ocr.recognize_image(img_path,
                max_tokens=get('ocr', 'max_tokens', default=3072))
            blocks = parse_ocr_output(ocr_text)
            blocks = merge_split_blocks(blocks)

            # 分类 + 裁剪
            page_blocks = []
            for i, b in enumerate(blocks):
                bt = b['type']
                if bt in HIDE_TYPES:
                    continue
                # 兜底：未知类型 → 原样输出，不翻译
                if bt not in ALL_KNOWN_TYPES:
                    en = _fix_latex(b['text'])
                    page_blocks.append({
                        'page': page_num+1, 'idx': i, 'type': bt,
                        'en': en, 'zh': en,
                        'passthrough': True, 'bbox': b['bbox'],
                    })
                    continue
                if bt in TEXT_TYPES or bt in PASSTHROUGH:
                    is_pt = bt in PASSTHROUGH
                    en = _fix_latex(b['text'])
                    page_blocks.append({
                        'page': page_num+1, 'idx': i, 'type': bt,
                        'en': en, 'zh': en if is_pt else '',
                        'passthrough': is_pt, 'bbox': b['bbox'],
                    })
                elif bt in IMAGE_TYPES and b['bbox']:
                    try:
                        fig_idx = len(task.figures)
                        fp = _crop(img_path, b['bbox'], pix.width, pix.height, task_id, page_num, fig_idx)
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
            all_page_blocks.append(page_blocks)

            # 发送 OCR 进度
            _emit(task_id, {"type": "ocr_progress",
                            "page": page_num+1, "total_pages": total_pages})
            print(f"  OCR page {page_num+1}/{total_pages}: {len(page_blocks)} blocks")

        # OCR 完成，释放模型
        ocr.close()
        doc.close()

        # 清理临时图片
        for p in img_paths:
            try: os.unlink(p)
            except OSError: pass

        # 跨页段落检测（找出跨页延续的 text block 对，翻译时合并、翻译后拆分）
        cross_page_pairs = find_cross_page_pairs(all_page_blocks)
        # 建立 block id → pair 的映射，方便翻译时查找
        cross_page_map = {}  # id(block_a) -> (block_a, block_b)
        for ba, bb in cross_page_pairs:
            cross_page_map[id(ba)] = (ba, bb)

        # 统计总 block 数
        total_blocks = sum(len(pb) for pb in all_page_blocks)
        print(f"[Phase 1] Done: {total_blocks} blocks across {total_pages} pages")

        # ════════════════════════════════════════════════════════
        #  Phase 2: 全量翻译（加载翻译模型，逐 block 处理）
        # ════════════════════════════════════════════════════════
        _emit(task_id, {"type": "phase", "phase": "translate",
                         "total_blocks": total_blocks})
        print(f"[Phase 2] Translate: {total_blocks} blocks")

        translator = SmartTranslator(
            model_path=trans_model,
            n_gpu_layers=get('gpu', 'trans_layers', default=99),
            verify=get('translation', 'verify', default=True))

        # 从第 0 页提取论文方向
        if all_page_blocks:
            first_page_text = [b for b in all_page_blocks[0]
                               if b['type'] == 'text' and not is_pseudo_title(b['en'], b['type'])]
            if first_page_text:
                abstract = max(first_page_text, key=lambda b: len(b['en']))
                translator.set_direction_from_abstract(abstract['en'])

        # 逐 block 翻译（保持文档顺序：页 → 块）
        # 收集所有被跨页合并吃掉的 block_b（翻译时已处理，遍历时跳过）
        consumed_blocks = set()
        for ba, bb in cross_page_pairs:
            consumed_blocks.add(id(bb))

        block_idx = 0
        for page_blocks in all_page_blocks:
            page_num = page_blocks[0]['page'] if page_blocks else 0
            _emit(task_id, {"type": "page_start", "page": page_num})

            for b in page_blocks:
                if cancel_event.is_set(): raise InterruptedError("Cancelled")

                # 如果这个 block 已经被跨页合并处理过了，跳过
                if id(b) in consumed_blocks:
                    block_idx += 1
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

                    # 跨页合并翻译：如果是 pair 的 block_a，合并翻译后拆分
                    if id(b) in cross_page_map:
                        ba, bb = cross_page_map[id(b)]
                        combined_en = ba['en'].rstrip() + ' ' + bb['en'].lstrip()
                        try:
                            combined_zh = translator.translate_block(combined_en, btype)
                        except Exception as e:
                            combined_zh = f"[ERROR: {e}]"
                        if combined_zh is None:
                            combined_zh = combined_en

                        # 拆分翻译回两个 block
                        zh1, zh2 = split_translation(
                            combined_en, combined_zh, len(ba['en']), len(bb['en']))
                        ba['zh'] = zh1
                        bb['zh'] = zh2

                        # 发送 block_a
                        _emit(task_id, {"type":"block_done","page":ba['page'],"idx":ba['idx'],
                                        "block_type":ba['type'],"en":ba['en'],"zh":zh1,"verified":True})
                        # 发送 block_b（已翻译，保留在原始页）
                        _emit(task_id, {"type":"block_done","page":bb['page'],"idx":bb['idx'],
                                        "block_type":bb['type'],"en":bb['en'],"zh":zh2,"verified":True})
                    else:
                        # 普通 block，正常翻译
                        try:
                            zh = translator.translate_block(text, btype)
                        except Exception as e:
                            zh = f"[ERROR: {e}]"

                        if zh is None:  # skipped (title / pseudo-title)
                            zh = text
                        b['zh'] = zh

                        _emit(task_id, {"type":"block_done","page":b['page'],"idx":b['idx'],
                                        "block_type":btype,"en":text,"zh":zh,"verified":True})

                block_idx += 1
                # 发送翻译进度
                _emit(task_id, {"type": "translate_progress",
                                "done": block_idx, "total": total_blocks})

            _emit(task_id, {"type": "page_done", "page": page_num, "blocks": len(page_blocks)})
            task.blocks.extend(page_blocks)

        print(f"  Translation stats: {translator.stats}")
        translator.close()
        _emit(task_id, {"type": "complete"})
        task_manager.update(task_id, status="completed")

    except InterruptedError:
        task_manager.update(task_id, status="failed", error="Cancelled")
    except Exception as e:
        import traceback; traceback.print_exc()
        task_manager.update(task_id, status="failed", error=str(e))
    finally:
        remove_event_queue(task_id)


# ── Helpers ──

def _fix_latex(text: str) -> str:
    import re
    text = re.sub(r'\\\[', '$$', text)
    text = re.sub(r'\\\]', '$$', text)
    text = re.sub(r'\\\(', '$', text)
    text = re.sub(r'\\\)', '$', text)
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


def _crop(img_path: str, bbox_1024: list, iw: int, ih: int, tid: str, pn: int, fi: int) -> str:
    from PIL import Image
    sx, sy = iw/1024.0, ih/1024.0
    x1, y1 = int(bbox_1024[0]*sx), int(bbox_1024[1]*sy)
    x2, y2 = int(bbox_1024[2]*sx), int(bbox_1024[3]*sy)
    img = Image.open(img_path)
    cropped = img.crop((x1, y1, x2, y2))
    d = os.path.join(tempfile.gettempdir(), f"ppt_{tid}_figures")
    os.makedirs(d, exist_ok=True)
    out = os.path.join(d, f"p{pn}_f{fi}.png")
    cropped.save(out)
    return out
