"""
Multi-Model OCR Inference Engine Architecture
Supports:
1. Unlimited-OCR (Baidu deepseek2-ocr, <|det|> detection tokens format)
2. OvisOCR2 (Qwen2.5-VL derivative, end-to-end Markdown format with embedded bbox image tags)
"""
import os, sys, re
from abc import ABC, abstractmethod
from typing import Optional, List, Dict, Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from infer.llama_binding import LlamaModel, llama_token, _lib as llama_lib
from infer.mtmd_binding import MtmdOCR, _mtmd as mtmd_lib
from infer.ovis_parser import parse_ovis_markdown


class BaseOCREngine(ABC):
    """Abstract Base Class for all OCR Engines in LunePaper."""

    @abstractmethod
    def recognize_image(self, image_path: str, max_tokens: int = 4096,
                        prompt: Optional[str] = None,
                        penalty_last_n: int = 256,
                        penalty_repeat: float = 1.20,
                        penalty_freq: float = 0.20,
                        penalty_present: float = 0.05) -> str:
        """Run multimodal OCR inference on a single image and return raw output text."""
        pass

    @abstractmethod
    def parse_output(self, raw_text: str) -> List[Dict[str, Any]]:
        """Parse model-specific raw output into standardized LunePaper block dicts."""
        pass

    def recognize_page_pdf(self, page, dpi: int = 200, max_tokens: int = 2048) -> str:
        """OCR a PyMuPDF page object. Renders to temporary image first."""
        import tempfile
        pix = page.get_pixmap(dpi=dpi)
        with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as f:
            pix.save(f.name)
            result = self.recognize_image(f.name, max_tokens=max_tokens)
        try:
            os.unlink(f.name)
        except OSError:
            pass
        return result

    @abstractmethod
    def close(self):
        """Release LLM and multimodal projector contexts."""
        pass


class UnlimitedOCREngine(BaseOCREngine):
    """Baidu Unlimited-OCR (deepseek2-ocr architecture with <|det|> tokens)."""

    def __init__(self, model_path: Optional[str] = None,
                 mmproj_path: Optional[str] = None,
                 n_gpu_layers: int = 99, n_ctx: int = 8192):
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if model_path is None:
            model_path = os.path.join(base, 'Unlimited-OCR-Q8_0.gguf')
        if mmproj_path is None:
            mmproj_path = os.path.join(base, 'mmproj-Unlimited-OCR-F16.gguf')

        self.engine_type = "unlimited"
        self.llm = LlamaModel(model_path, n_gpu_layers=n_gpu_layers, n_ctx=n_ctx)
        self.mtmd = MtmdOCR(mmproj_path, self.llm.model, use_gpu=True)
        self.marker = self.mtmd.get_marker()
        print(f"[Unlimited-OCR] Ready. Marker: {self.marker!r}, n_ctx={n_ctx}")

    def recognize_image(self, image_path: str, max_tokens: int = 4096,
                        prompt: Optional[str] = None,
                        penalty_last_n: int = 256,
                        penalty_repeat: float = 1.20,
                        penalty_freq: float = 0.20,
                        penalty_present: float = 0.05) -> str:
        if prompt is None:
            prompt = f"{self.marker}document parsing."

        wrapper = self.mtmd.load_bitmap_from_file(image_path)
        chunks = self.mtmd.tokenize_prompt_with_images(prompt, [wrapper.bitmap])

        mem = llama_lib.llama_get_memory(self.llm.ctx)
        llama_lib.llama_memory_clear(mem, True)
        self.mtmd.eval_chunks(self.llm.ctx, chunks)

        sparams = llama_lib.llama_sampler_chain_default_params()
        chain = llama_lib.llama_sampler_chain_init(sparams)
        penalties = llama_lib.llama_sampler_init_penalties(
            penalty_last_n, penalty_repeat, penalty_freq, penalty_present
        )
        llama_lib.llama_sampler_chain_add(chain, penalties)
        llama_lib.llama_sampler_chain_add(chain, llama_lib.llama_sampler_init_greedy())

        gen_tokens = []
        for _ in range(max_tokens):
            token_id = llama_lib.llama_sampler_sample(chain, self.llm.ctx, -1)
            if token_id == self.llm.eos_token or token_id == self.llm.eot_token:
                break
            gen_tokens.append(token_id)
            token_arr = (llama_token * 1)(token_id)
            batch = llama_lib.llama_batch_get_one(token_arr, 1)
            if llama_lib.llama_decode(self.llm.ctx, batch) != 0:
                break

        if len(gen_tokens) >= max_tokens:
            print(f"[OCR Warning] Image {os.path.basename(image_path)} reached max_tokens ({max_tokens}) without EOS.")

        llama_lib.llama_sampler_free(chain)
        text = self._detokenize_raw(gen_tokens)

        self.mtmd.free_chunks(chunks)
        self.mtmd.free_bitmap(wrapper)
        return text

    def _detokenize_raw(self, tokens: List[int]) -> str:
        from infer.llama_binding import _gpt2_byte_decode
        raw_parts = []
        for t in tokens:
            s = llama_lib.llama_vocab_get_text(self.llm.vocab, t)
            if s:
                raw_parts.append(s)
        if not raw_parts:
            return ""
        raw_bytes = b''.join(raw_parts)
        raw_str = raw_bytes.decode('utf-8', errors='replace')
        return _gpt2_byte_decode(raw_str)

    def parse_output(self, raw_text: str) -> List[Dict[str, Any]]:
        return parse_ocr_output(raw_text)

    def close(self):
        self.mtmd.close()
        self.llm.close()


class OvisOCREngine(BaseOCREngine):
    """OvisOCR2 (Qwen2.5-VL architecture, end-to-end Markdown output)."""

    def __init__(self, model_path: Optional[str] = None,
                 mmproj_path: Optional[str] = None,
                 n_gpu_layers: int = 99, n_ctx: int = 8192):
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if model_path is None:
            model_path = os.path.join(base, 'OvisOCR2-Q8_0.gguf')
        if mmproj_path is None:
            mmproj_path = os.path.join(base, 'mmproj-BF16.gguf')

        self.engine_type = "ovis"
        self.llm = LlamaModel(model_path, n_gpu_layers=n_gpu_layers, n_ctx=n_ctx)
        self.mtmd = MtmdOCR(mmproj_path, self.llm.model, use_gpu=True)
        self.marker = self.mtmd.get_marker()
        print(f"[OvisOCR2] Ready. Marker: {self.marker!r}, n_ctx={n_ctx}")

    def recognize_image(self, image_path: str, max_tokens: int = 4096,
                        prompt: Optional[str] = None,
                        penalty_last_n: int = 256,
                        penalty_repeat: float = 1.20,
                        penalty_freq: float = 0.20,
                        penalty_present: float = 0.05) -> str:
        if prompt is None:
            # Official Qwen/Ovis chat template for OCR
            prompt = (
                f"<|im_start|>user\n{self.marker}Extract all readable content from the image in "
                f"natural human reading order and output the result as a single Markdown document.<|im_end|>\n"
                f"<|im_start|>assistant\n<think>\n\n</think>\n\n"
            )

        wrapper = self.mtmd.load_bitmap_from_file(image_path)
        chunks = self.mtmd.tokenize_prompt_with_images(prompt, [wrapper.bitmap])

        mem = llama_lib.llama_get_memory(self.llm.ctx)
        llama_lib.llama_memory_clear(mem, True)
        self.mtmd.eval_chunks(self.llm.ctx, chunks)

        sparams = llama_lib.llama_sampler_chain_default_params()
        chain = llama_lib.llama_sampler_chain_init(sparams)
        penalties = llama_lib.llama_sampler_init_penalties(
            penalty_last_n, penalty_repeat, penalty_freq, penalty_present
        )
        llama_lib.llama_sampler_chain_add(chain, penalties)
        llama_lib.llama_sampler_chain_add(chain, llama_lib.llama_sampler_init_greedy())

        gen_tokens = []
        for _ in range(max_tokens):
            token_id = llama_lib.llama_sampler_sample(chain, self.llm.ctx, -1)
            if token_id == self.llm.eos_token or token_id == self.llm.eot_token:
                break
            gen_tokens.append(token_id)
            token_arr = (llama_token * 1)(token_id)
            batch = llama_lib.llama_batch_get_one(token_arr, 1)
            if llama_lib.llama_decode(self.llm.ctx, batch) != 0:
                break

        if len(gen_tokens) >= max_tokens:
            print(f"[Ovis Warning] Image {os.path.basename(image_path)} reached max_tokens ({max_tokens}) without EOS.")

        llama_lib.llama_sampler_free(chain)
        text = self.llm.detokenize(gen_tokens)

        self.mtmd.free_chunks(chunks)
        self.mtmd.free_bitmap(wrapper)
        return text

    def parse_output(self, raw_text: str) -> List[Dict[str, Any]]:
        return parse_ovis_markdown(raw_text)

    def close(self):
        self.mtmd.close()
        self.llm.close()


class OCREngineFactory:
    """Factory to create OCR engines based on engine ID or config."""

    @staticmethod
    def create_engine(engine_type: Optional[str] = None,
                      model_path: Optional[str] = None,
                      mmproj_path: Optional[str] = None,
                      n_gpu_layers: int = 99,
                      n_ctx: int = 8192) -> BaseOCREngine:
        from config import get_ocr_engine_config, get as cfg_get

        target = (engine_type or cfg_get('models', 'ocr_default', default='unlimited')).lower().strip()
        engine_cfg = get_ocr_engine_config(target)

        m_path = model_path or engine_cfg.get('model_path')
        mm_path = mmproj_path or engine_cfg.get('mmproj_path')
        ctx = n_ctx or engine_cfg.get('n_ctx', 8192)

        if target == 'ovis':
            return OvisOCREngine(
                model_path=m_path,
                mmproj_path=mm_path,
                n_gpu_layers=n_gpu_layers,
                n_ctx=ctx
            )
        else:
            return UnlimitedOCREngine(
                model_path=m_path,
                mmproj_path=mm_path,
                n_gpu_layers=n_gpu_layers,
                n_ctx=ctx
            )


# Backward-compatible default OCREngine class alias
class OCREngine(UnlimitedOCREngine):
    """Default OCREngine alias pointing to Unlimited-OCR for backward compatibility."""
    pass


def parse_ocr_output(text: str) -> List[Dict[str, Any]]:
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
            'passthrough': match.group(1) in {
                'title', 'ref_text', 'equation', 'table', 'aside_text',
                'header', 'footer', 'algorithm'
            }
        })
    return blocks
