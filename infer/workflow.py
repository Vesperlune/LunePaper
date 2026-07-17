"""
Phase 3: Streaming Translation Workflow (LangGraph)

Flow:
  init → process_page ⟲ (per-page loop) → summarize → END

Each page: load OCR → recognize → unload OCR → translate blocks (with context)
"""
import os, sys, time, tempfile
from typing import TypedDict, Annotated, List
import operator

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.add_dll_directory(os.getcwd())
os.add_dll_directory(r'C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.6\bin')

from langgraph.graph import StateGraph, END

# ── Module-level model singletons (shared across LangGraph nodes) ──
_translator = None   # ContextWindowTranslator, loaded once
_ocr_engine = None    # OCREngine, loaded/unloaded per page


# ═══════════════════════════════════════════════════════════════
# State
# ═══════════════════════════════════════════════════════════════

class PageResult(TypedDict, total=False):
    page_num: int
    blocks: list      # [{type, en_text, zh_text, bbox}, ...]
    ocr_time: float
    trans_time: float
    verified: int
    retried: int


class TranslationState(TypedDict, total=False):
    # Input
    doc_path: str
    dpi: int
    ocr_model_path: str
    mmproj_path: str
    trans_model_path: str

    # init node
    page_count: int
    page_images: list[str]
    current_page: int

    # Accumulated results
    results: Annotated[list, operator.add]

    # summarize node
    quality: dict
    output_path: str
    completion_status: str


# ═══════════════════════════════════════════════════════════════
# Model lifecycle helpers
# ═══════════════════════════════════════════════════════════════

def _load_translator(model_path: str):
    global _translator
    if _translator is None:
        from infer.translate_v2 import ContextWindowTranslator
        _translator = ContextWindowTranslator(
            model_path=model_path, n_gpu_layers=99,
            verify=True)
        _translator.reset_context()
    return _translator


def _load_ocr(model_path: str, mmproj_path: str):
    global _ocr_engine
    from infer.ocr import OCREngine
    _ocr_engine = OCREngine(
        model_path=model_path, mmproj_path=mmproj_path,
        n_gpu_layers=99, n_ctx=4096)
    return _ocr_engine


def _unload_ocr():
    global _ocr_engine
    if _ocr_engine:
        _ocr_engine.close()
        _ocr_engine = None


def _unload_translator():
    global _translator
    if _translator:
        _translator.close()
        _translator = None


# ═══════════════════════════════════════════════════════════════
# Node 1: init — render PDF pages, load translation model
# ═══════════════════════════════════════════════════════════════

def init(state: TranslationState) -> dict:
    """
    Preprocess: render all PDF pages to images, load translation model.
    """
    import fitz

    doc = fitz.open(state["doc_path"])
    page_count = len(doc)
    tmpdir = tempfile.mkdtemp(prefix='ppt_workflow_')

    images = []
    for i in range(page_count):
        page = doc[i]
        pix = page.get_pixmap(dpi=state.get("dpi", 144))
        path = os.path.join(tmpdir, f'page_{i:04d}.png')
        pix.save(path)
        images.append(path)
    doc.close()

    # Warm up translation model (stays loaded for entire workflow)
    _load_translator(state["trans_model_path"])

    print(f"[init] {page_count} pages rendered, translator loaded")

    return {
        "page_count": page_count,
        "page_images": images,
        "current_page": 0,
        "completion_status": "running",
    }


# ═══════════════════════════════════════════════════════════════
# Node 2: process_page — OCR + translate single page
# ═══════════════════════════════════════════════════════════════

def process_page(state: TranslationState) -> dict:
    """
    Process one page: load OCR → recognize → unload → translate blocks.
    This is called once per page via the conditional loop.
    """
    from infer.ocr import parse_ocr_output

    page_num = state["current_page"]
    img_path = state["page_images"][page_num]

    # ── Step 1: OCR (load → recognize → unload) ──
    t0 = time.time()
    ocr = _load_ocr(state["ocr_model_path"], state["mmproj_path"])
    ocr_text = ocr.recognize_image(img_path, max_tokens=1024)
    _unload_ocr()

    blocks = parse_ocr_output(ocr_text)
    text_blocks = [
        {'type': b['type'], 'bbox': b['bbox'], 'en_text': b['text']}
        for b in blocks
        if b['type'] in ('text', 'title', 'aside_text', 'caption')
        and b['text'] and len(b['text'].strip()) > 3
    ]
    ocr_time = time.time() - t0

    # ── Step 2: Translate (translator already loaded) ──
    t1 = time.time()
    translator = _translator

    verified = 0
    retried = 0
    for block in text_blocks:
        text = block['en_text']
        try:
            zh = translator.translate_with_context(text, max_tokens=512)
        except Exception as e:
            zh = f"[ERROR: {e}]"

        block['zh_text'] = zh

        # Track verification from translator's internal history
        if translator._history:
            last = translator._history[-1]
            if last.get('verified'):
                verified += 1
            if last.get('retries', 0) > 0:
                retried += 1

    trans_time = time.time() - t1

    pct = (page_num + 1) / state["page_count"] * 100
    print(f"  [{pct:3.0f}%] Page {page_num + 1}: "
          f"{len(text_blocks)} blocks | OCR {ocr_time:.1f}s | "
          f"TR {trans_time:.1f}s | OK:{verified} RT:{retried}")

    return {
        "current_page": page_num + 1,
        "results": [{
            "page_num": page_num + 1,
            "blocks": text_blocks,
            "ocr_time": ocr_time,
            "trans_time": trans_time,
            "verified": verified,
            "retried": retried,
        }],
    }


# ═══════════════════════════════════════════════════════════════
# Node 3: summarize — quality report + output
# ═══════════════════════════════════════════════════════════════

def summarize(state: TranslationState) -> dict:
    """
    Aggregate results, generate quality report, write bilingual output.
    """
    results = state["results"]
    translator = _translator

    total_blocks = sum(len(r["blocks"]) for r in results)
    total_verified = sum(r.get("verified", 0) for r in results)
    total_retried = sum(r.get("retried", 0) for r in results)
    total_ocr = sum(r.get("ocr_time", 0) for r in results)
    total_trans = sum(r.get("trans_time", 0) for r in results)
    total_time = total_ocr + total_trans

    quality = {
        "pages": len(results),
        "total_blocks": total_blocks,
        "verified": total_verified,
        "retried": total_retried,
        "pass_rate": f"{total_verified}/{total_blocks}"
                     f" ({100*total_verified/max(1,total_blocks):.0f}%)",
        "ocr_time": f"{total_ocr:.0f}s",
        "trans_time": f"{total_trans:.0f}s",
        "total_time": f"{total_time:.0f}s",
    }

    # Write bilingual markdown
    output_path = state["doc_path"].replace(".pdf", "_bilingual.md")
    _write_output(output_path, state["doc_path"], results, quality)

    # Cleanup temp images
    for img in state.get("page_images", []):
        try:
            os.unlink(img)
        except OSError:
            pass
    tmpdir = os.path.dirname(state["page_images"][0]) if state["page_images"] else ""
    if tmpdir:
        try:
            os.rmdir(tmpdir)
        except OSError:
            pass

    # Shutdown translator
    vstats = translator.stats if translator else {}
    _unload_translator()

    print(f"\n[summarize] Done: {quality['total_blocks']} blocks in {quality['total_time']}")
    print(f"  Verified: {quality['pass_rate']}")
    print(f"  Retried:  {total_retried}")
    print(f"  Output:   {output_path}")

    return {
        "quality": quality,
        "output_path": output_path,
        "completion_status": "completed",
    }


def _write_output(output_path: str, doc_path: str,
                  results: list, quality: dict):
    """Write complete bilingual Markdown output."""
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(f"# {os.path.basename(doc_path)}\n\n")
        f.write(f"> Streamed OCR + Context-Window Translation + Anti-Hallucination\n\n")

        f.write("## Quality Report\n\n")
        f.write("| Metric | Value |\n|---|---|\n")
        for k, v in quality.items():
            f.write(f"| {k.replace('_', ' ').title()} | {v} |\n")
        f.write("\n")

        for r in results:
            f.write(f"## Page {r['page_num']}\n\n")
            for block in r["blocks"]:
                f.write(f"**[{block['type']}]**\n\n")
                f.write(f"> {block['en_text']}\n\n")
                zh = block.get('zh_text', '')
                if zh.startswith('[ERROR'):
                    f.write(f"❌ {zh}\n\n")
                else:
                    f.write(f"{zh}\n\n")
            f.write("---\n\n")


# ═══════════════════════════════════════════════════════════════
# Conditional routing
# ═══════════════════════════════════════════════════════════════

def should_continue(state: TranslationState) -> str:
    """Route: next page or finish?"""
    if state["current_page"] < state["page_count"]:
        return "process_page"
    return "summarize"


# ═══════════════════════════════════════════════════════════════
# Graph construction
# ═══════════════════════════════════════════════════════════════

def build_workflow() -> StateGraph:
    workflow = StateGraph(TranslationState)

    workflow.add_node("init", init)
    workflow.add_node("process_page", process_page)
    workflow.add_node("summarize", summarize)

    workflow.set_entry_point("init")
    workflow.add_edge("init", "process_page")

    workflow.add_conditional_edges(
        "process_page",
        should_continue,
        {
            "process_page": "process_page",
            "summarize": "summarize",
        }
    )

    workflow.add_edge("summarize", END)

    return workflow.compile()


# ═══════════════════════════════════════════════════════════════
# Run
# ═══════════════════════════════════════════════════════════════

if __name__ == '__main__':
    import time as _time

    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    initial_state: TranslationState = {
        "doc_path": os.path.join(base, "2606.23050v1.pdf"),
        "dpi": 144,
        "ocr_model_path": os.path.join(base, "Unlimited-OCR-Q8_0.gguf"),
        "mmproj_path": os.path.join(base, "mmproj-Unlimited-OCR-F16.gguf"),
        "trans_model_path": os.path.join(base, "Hy-MT2-1.8B-Q8_0.gguf"),
    }

    # 2-page quick test
    graph = build_workflow()
    t0 = _time.time()

    # Override page_count to limit to 2 pages for quick test
    final_state = graph.invoke(initial_state,
        config={"recursion_limit": 50})  # enough for 14 iterations

    # Use .stream() for real-time page-by-page progress
    for event in graph.stream(initial_state):
        node_name = list(event.keys())[0]
        if node_name == "process_page":
            pr = event["process_page"]["results"][0]
            print(f">> Page {pr['page_num']}: {len(pr['blocks'])} blocks | "
                  f"OCR {pr['ocr_time']:.1f}s TR {pr['trans_time']:.1f}s | "
                  f"OK:{pr['verified']} RT:{pr['retried']}")
        elif node_name == "summarize":
            q = event["summarize"]["quality"]
            print(f"\nQuality: {q['total_blocks']} blocks | "
                  f"Pass: {q['pass_rate']} | Total: {q['total_time']}")

    elapsed = _time.time() - t0
    print(f"\nTotal: {elapsed:.0f}s")
