"""
Unlimited-OCR Inference Script
Based on official Baidu Unlimited-OCR API:
  - Prompts: "<image>document parsing." or "<image>Free OCR."
  - Token format: <|det|>TYPE [x1,y1,x2,y2]<|/det|>TEXT
  - Requires skip_special_tokens=False (keep detection markers)
"""
import os, sys, re
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from infer.llama_binding import LlamaModel, llama_token, _lib as llama_lib
from infer.mtmd_binding import MtmdOCR, _mtmd as mtmd_lib


class OCREngine:
    """OCR using Baidu Unlimited-OCR (deepseek2-ocr architecture)."""

    def __init__(self, model_path: str = None, mmproj_path: str = None,
                 n_gpu_layers: int = 99, n_ctx: int = 4096):
        if model_path is None:
            base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            model_path = os.path.join(base, 'Unlimited-OCR-Q8_0.gguf')
        if mmproj_path is None:
            base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            mmproj_path = os.path.join(base, 'mmproj-Unlimited-OCR-F16.gguf')

        self.llm = LlamaModel(model_path, n_gpu_layers=n_gpu_layers, n_ctx=n_ctx)
        self.mtmd = MtmdOCR(mmproj_path, self.llm.model, use_gpu=True)
        self.marker = self.mtmd.get_marker()
        print(f"OCR Engine ready. Marker: {self.marker!r}, n_ctx={n_ctx}")

    def recognize_image(self, image_path: str, max_tokens: int = 2048,
                        prompt: str = None) -> str:
        """
        Run OCR on a single image.

        Args:
            image_path: Path to PNG/JPG image
            max_tokens: Max output tokens
            prompt: OCR prompt. Default: "<marker>document parsing."

        Returns:
            Raw OCR output text with <|det|> bounding box annotations
        """
        if prompt is None:
            # Official prompt from Baidu docs
            prompt = f"{self.marker}document parsing."

        # Load image
        wrapper = self.mtmd.load_bitmap_from_file(image_path)

        # Tokenize with parse_special=True (keep <|det|> markers)
        chunks = self.mtmd.tokenize_prompt_with_images(
            prompt, [wrapper.bitmap])

        # Clear KV cache and eval
        mem = llama_lib.llama_get_memory(self.llm.ctx)
        llama_lib.llama_memory_clear(mem, True)
        self.mtmd.eval_chunks(self.llm.ctx, chunks)

        # Generate with greedy sampling (temp=0 from official docs)
        sparams = llama_lib.llama_sampler_chain_default_params()
        chain = llama_lib.llama_sampler_chain_init(sparams)
        llama_lib.llama_sampler_chain_add(chain, llama_lib.llama_sampler_init_greedy())

        gen_tokens = []
        for i in range(max_tokens):
            token_id = llama_lib.llama_sampler_sample(chain, self.llm.ctx, -1)
            if token_id == self.llm.eos_token or token_id == self.llm.eot_token:
                break
            gen_tokens.append(token_id)
            token_arr = (llama_token * 1)(token_id)
            batch = llama_lib.llama_batch_get_one(token_arr, 1)
            if llama_lib.llama_decode(self.llm.ctx, batch) != 0:
                break

        llama_lib.llama_sampler_free(chain)

        # Detokenize: use raw bytes approach to avoid losing special tokens
        text = self._detokenize_raw(gen_tokens)

        # Cleanup
        self.mtmd.free_chunks(chunks)
        self.mtmd.free_bitmap(wrapper)

        return text

    def _detokenize_raw(self, tokens: list[int]) -> str:
        """Detokenize preserving all tokens including special/control tokens."""
        from infer.llama_binding import _gpt2_byte_decode
        raw_parts = []
        for t in tokens:
            s = llama_lib.llama_vocab_get_text(self.llm.vocab, t)
            if s:
                raw_parts.append(s)
            # Note: some control tokens return empty bytes; skip them
        if not raw_parts:
            return ""
        raw_bytes = b''.join(raw_parts)
        raw_str = raw_bytes.decode('utf-8', errors='replace')
        return _gpt2_byte_decode(raw_str)

    def recognize_page_pdf(self, page, dpi: int = 200,
                           max_tokens: int = 2048) -> str:
        """OCR a PyMuPDF page object. Renders to temp image first."""
        import tempfile
        pix = page.get_pixmap(dpi=dpi)
        with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as f:
            pix.save(f.name)
            result = self.recognize_image(f.name, max_tokens=max_tokens)
        os.unlink(f.name)
        return result

    def close(self):
        self.mtmd.close()
        self.llm.close()


def parse_ocr_output(text: str) -> list[dict]:
    """
    Parse Unlimited-OCR output into structured blocks.
    Format: <|det|>TYPE [x1, y1, x2, y2]<|/det|>TEXT
    """
    blocks = []
    pattern = re.compile(
        r'<\|det\|>(\w+)\s*\[(\d+),\s*(\d+),\s*(\d+),\s*(\d+)\]<\|/det\|>(.*?)(?=<\|det\||$)',
        re.DOTALL)
    for match in pattern.finditer(text):
        blocks.append({
            'type': match.group(1),
            'bbox': [int(match.group(i)) for i in range(2, 6)],
            'text': match.group(6).strip(),
        })
    return blocks


# Test
if __name__ == '__main__':
    import sys, fitz
    from collections import Counter
    sys.stdout.reconfigure(encoding='utf-8')

    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    test_dir = r'C:\Users\YOGA\Desktop\论文测试集'

    print("Loading OCR engine...")
    engine = OCREngine()

    global_types = Counter()
    global_blocks = 0
    global_pages = 0

    pdfs = sorted([f for f in os.listdir(test_dir) if f.endswith('.pdf')])
    print(f"Found {len(pdfs)} PDFs\n")

    for pdf_name in pdfs:
        pdf_path = os.path.join(test_dir, pdf_name)
        doc = fitz.open(pdf_path)
        total_pages = len(doc)
        print(f"{'='*60}")
        print(f"PDF: {pdf_name} ({total_pages} pages)")
        print(f"{'='*60}")

        page_types = Counter()

        for page_num in range(total_pages):
            page = doc[page_num]
            pix = page.get_pixmap(dpi=144)
            img_path = os.path.join(base, '_test_page.png')
            pix.save(img_path)

            result = engine.recognize_image(img_path, max_tokens=4096)
            blocks = parse_ocr_output(result)

            for b in blocks:
                page_types[b['type']] += 1
                global_types[b['type']] += 1
                global_blocks += 1

            print(f"  P{page_num+1:2d}: {len(blocks):3d} blocks | {', '.join(f'{t}({c})' for t,c in sorted(page_types.items()))}")
            global_pages += 1
            os.unlink(img_path)

        print(f"  >> Subtotal: {sum(page_types.values())} blocks, types: {dict(page_types.most_common())}\n")
        doc.close()

    print(f"\n{'#'*60}")
    print(f"GRAND TOTAL: {global_blocks} blocks across {global_pages} pages in {len(pdfs)} PDFs")
    print(f"ALL UNIQUE TYPES ({len(global_types)}):")
    for t, c in global_types.most_common():
        print(f"  {t:20s} x{c}")
    print(f"{'#'*60}")

    engine.close()
