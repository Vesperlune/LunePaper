"""
Phase 5: Smart Translator (Academic Precision & Generalizable Terminology V2)
  - Multi-tier Academic Glossary & Dynamic Constraint Injection (infer.glossary)
  - Native ChatML / Hunyuan MT special token prompting with multi-turn sliding context
  - Unicode Entity Masking (⟪M0⟫, ⟪R0⟫, ⟪U0⟫) with fuzzy regex unmasking
  - Overlap-aware long paragraph chunking (sentence boundary + sliding overlap)
  - Multi-dimensional Quality Gate (Numerical invariance, polarity check, length ratio)
  - Post-correction of MT artifacts & "translationese"
  - Pseudo-title detection, OCR block merging, cross-page pair handling
"""
import os, sys, re, hashlib
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from infer.llama_binding import LlamaModel
from infer.glossary import AcademicGlossaryManager

# ── Base System Prompt ──

BASE_ACADEMIC_SYSTEM_PROMPT = """你是一名资深学术翻译专家。请将用户输入的英文学术文本翻译为严谨、规范、地道且符合中文学术出版标准的简体中文。
翻译准则：
1. 风格严谨客观，符合中文科技论文写作规范，杜绝欧化长句与生硬直译。
2. 专业术语务必准确规范，同篇论文术语表达前后严格统一。
3. 文本中的数学公式、特殊占位符（如 ⟪M0⟫、⟪R0⟫、⟪U0⟫ 等）以及数值、符号和单位必须严格原样保留，切勿删改或漏译。"""

DIRECTION_PROMPT = """从以下学术论文摘要提取研究领域核心关键词，用·连接，不超过15字。只输出关键词：

{abstract}

关键词："""

# Fallback plain prompts for non-chat models
SHORT_PROMPT = """【论文方向】{direction}
{style}

将以下短文本翻译为中文，只输出翻译结果：

{text}

中文："""

NORMAL_PROMPT = """【论文方向】{direction}
{style}

将以下英文学术文本翻译为中文，只输出翻译结果：

{text}

中文："""

CONTEXT_PROMPT = """【论文方向】{direction}
{style}

上文参考（保持术语风格一致）：
英文：{prev_en}
中文：{prev_zh}

将以下英文学术文本翻译为中文，只输出翻译结果：

{text}

中文："""

BACK_PROMPT = """中文：该模型取得了当前最优结果。
英文：The model achieves state-of-the-art results.

中文：{source}
英文："""


# ═══════════════════════════════════════════════
# Pseudo-title detection
# ═══════════════════════════════════════════════

HEADING_WORDS = {
    'abstract', 'introduction', 'conclusion', 'references',
    'acknowledgments', 'acknowledgements', 'contents', 'summary',
    'appendix', 'related works', 'background', 'methodology',
    'discussion', 'future work', 'limitations', 'preface', 'foreword',
}

def is_pseudo_title(text: str, block_type: str = 'text') -> bool:
    """Detect text blocks that are actually titles/headings."""
    from config import get as cfg
    text = text.strip()
    length = len(text)
    max_len = cfg('pseudo_title', 'max_len', default=40)
    heading_max = cfg('pseudo_title', 'heading_max_len', default=100)

    # If it ends with typical sentence punctuation, it is almost certainly a normal sentence, not a title
    if text.endswith(('.', '?', '!', '."', '.)', '.\"')):
        return False

    # 1. Very short and without sentence punctuation → likely a heading
    if length < max_len:
        return True

    # 2. Known heading words
    if text.lower().rstrip('.') in HEADING_WORDS:
        return True

    # 3. Numbered heading (e.g. "3.4.2. KV cache management")
    if re.match(r'^\d+(\.\d+)*\.?\s+\w', text) and length < heading_max:
        return True

    # 4. Short + Title Case + no sentence end punctuation
    words = text.split()
    if length < heading_max and len(words) <= 8:
        caps = [w for w in words if w and w[0].isalpha()]
        if caps and all(w[0].isupper() for w in caps):
            return True

    return False


# ═══════════════════════════════════════════════
# OCR block merging
# ═══════════════════════════════════════════════

def merge_split_blocks(blocks: list) -> list:
    """Merge adjacent text blocks that OCR incorrectly split."""
    if not blocks:
        return blocks

    merged = [dict(blocks[0])]

    for b in blocks[1:]:
        prev = merged[-1]
        if _should_merge(prev, b):
            prev['text'] = prev['text'] + ' ' + b['text']
            # expand bbox to encompass both
            prev['bbox'] = [
                min(prev['bbox'][0], b['bbox'][0]),
                min(prev['bbox'][1], b['bbox'][1]),
                max(prev['bbox'][2], b['bbox'][2]),
                max(prev['bbox'][3], b['bbox'][3]),
            ]
        else:
            merged.append(dict(b))
    return merged


def _should_merge(prev: dict, cur: dict) -> bool:
    if prev.get('type') != 'text' or cur.get('type') != 'text':
        return False
    pt = prev['text'].rstrip()
    ct = cur['text'].lstrip()
    if not pt or not ct:
        return False
    # Previous doesn't end with sentence terminator
    if pt.endswith(('.', '?', '!', '."', '.)', '.\"')):
        return False
    # Current starts lowercase (continuation)
    if ct[0].isupper():
        return False
    # Bbox vertical proximity and column consistency
    if 'bbox' in prev and 'bbox' in cur:
        # Don't merge across different columns if their horizontal positions are far apart
        if abs(prev['bbox'][0] - cur['bbox'][0]) > 150:
            return False
        prev_bottom = prev['bbox'][3]
        cur_top = cur['bbox'][1]
        line_h = max(prev['bbox'][3] - prev['bbox'][1], 10)
        if cur_top - prev_bottom > line_h * 2.5:
            return False

    return True


def find_cross_page_pairs(page_blocks_list: list[list]) -> list[tuple]:
    """
    Find text block pairs that span across page boundaries.
    Returns list of (block_a, block_b) tuples where block_a is the last text
    on page N and block_b is the first text on page N+1, forming a continuation.
    Does NOT modify any blocks.
    """
    pairs = []
    if len(page_blocks_list) <= 1:
        return pairs

    for i in range(len(page_blocks_list) - 1):
        cur_page = page_blocks_list[i]
        next_page = page_blocks_list[i + 1]
        if not cur_page or not next_page:
            continue

        # Find last text block on current page (must be substantial, non-passthrough paragraph)
        last_text = None
        for j in range(len(cur_page) - 1, -1, -1):
            b = cur_page[j]
            if b.get('type') == 'text' and not b.get('passthrough'):
                txt = (b.get('en') or b.get('text', '')).strip()
                if len(txt) > 5 and not re.match(r'^[-—–\s]*(?:page\s+)?\d{1,4}[-—–\s]*$', txt, re.I):
                    last_text = b
                    break
        if last_text is None:
            continue

        # Find first text block on next page (must be substantial, non-passthrough paragraph)
        first_text = None
        for j in range(len(next_page)):
            b = next_page[j]
            if b.get('type') == 'text' and not b.get('passthrough'):
                txt = (b.get('en') or b.get('text', '')).strip()
                if len(txt) > 5 and not re.match(r'^[-—–\s]*(?:page\s+)?\d{1,4}[-—–\s]*$', txt, re.I):
                    first_text = b
                    break
        if first_text is None:
            continue

        # Check continuation conditions
        pt = (last_text.get('en') or last_text.get('text', '')).rstrip()
        ct = (first_text.get('en') or first_text.get('text', '')).lstrip()
        if not pt or not ct:
            continue
        # Skip blocks containing invalid markers (e.g. [Non-Text])
        if '[non-text]' in pt.lower() or '[non-text]' in ct.lower():
            continue
        if '[non text]' in pt.lower() or '[non text]' in ct.lower():
            continue
        if pt.endswith(('.', '?', '!', '."', '.)', '.\"')):
            continue
        if ct[0].isupper():
            continue

        pairs.append((last_text, first_text))
        print(f"  [cross-page pair] P{i+1} → P{i+2}: {len(pt)}+{len(ct)} chars")

    return pairs


def split_translation(combined_en: str, combined_zh: str,
                      part1_len: int, part2_len: int) -> tuple[str, str]:
    """
    Split a combined translation back into two parts.
    Tries to split at sentence boundaries; falls back to clause or proportional split.
    Guarantees non-empty outputs when inputs have content.
    """
    total = part1_len + part2_len
    if total == 0 or not combined_zh:
        return combined_zh, ''

    ratio = part1_len / total

    # Try splitting at sentence boundaries (Chinese punctuation)
    sentences = re.split(r'(?<=[。！？；\n])', combined_zh)
    sentences = [s for s in sentences if s.strip()]

    if len(sentences) >= 2:
        target_chars = int(len(combined_zh) * ratio)
        best_k = 1
        min_diff = float('inf')
        for k in range(1, len(sentences)):
            curr_len = sum(len(sentences[i]) for i in range(k))
            diff = abs(curr_len - target_chars)
            if diff < min_diff:
                min_diff = diff
                best_k = k
        zh1 = ''.join(sentences[:best_k])
        zh2 = ''.join(sentences[best_k:])
        if zh1.strip() and zh2.strip():
            return zh1, zh2

    # Fallback: Try clause boundaries (，)
    clauses = re.split(r'(?<=[，,])', combined_zh)
    clauses = [c for c in clauses if c.strip()]
    if len(clauses) >= 2:
        target_chars = int(len(combined_zh) * ratio)
        best_k = 1
        min_diff = float('inf')
        for k in range(1, len(clauses)):
            curr_len = sum(len(clauses[i]) for i in range(k))
            diff = abs(curr_len - target_chars)
            if diff < min_diff:
                min_diff = diff
                best_k = k
        zh1 = ''.join(clauses[:best_k])
        zh2 = ''.join(clauses[best_k:])
        if zh1.strip() and zh2.strip():
            return zh1, zh2

    # Final fallback: proportional split (ensure at least 1 char in each if possible)
    split_pos = max(1, min(len(combined_zh) - 1, int(len(combined_zh) * ratio)))
    return combined_zh[:split_pos], combined_zh[split_pos:]


# ═══════════════════════════════════════════════
# SmartTranslator V2
# ═══════════════════════════════════════════════

class SmartTranslator:
    """
    High-Precision Academic Translator:
    - Domain Glossary & Dynamic Constraint Injection
    - Hunyuan Native Chat Template + Multi-turn Context Sliding
    - Unicode Entity Masking (⟪M0⟫, ⟪R0⟫, ⟪U0⟫)
    - Overlap-aware Sentence Chunking
    - Quality Gate with Numerical & Polarity Invariance Verification
    - Automated Post-Correction
    """

    def __init__(self, model_path: str = None, n_gpu_layers: int = 99,
                 verify: bool = True, chunk_size: int = None,
                 verify_strategy: str = None, verify_audit_rate: float = None):
        from config import get as cfg
        if model_path is None:
            model_path = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                cfg('models', 'translation', default='Hy-MT2-1.8B-Q8_0.gguf'))

        self.llm = LlamaModel(model_path, n_gpu_layers=n_gpu_layers,
                              n_ctx=cfg('translation', 'n_ctx', default=2048),
                              n_threads=cfg('translation', 'n_threads', default=4))
        self.verify = verify
        self.chunk_size = chunk_size or cfg('translation', 'chunk_size', default=500)
        self.verify_strategy = (verify_strategy or cfg(
            'translation', 'verify_strategy', default='adaptive')).lower()
        if self.verify_strategy not in {'full', 'adaptive'}:
            raise ValueError("verify_strategy must be 'full' or 'adaptive'")
        self.verify_audit_rate = (
            cfg('translation', 'verify_audit_rate', default=0.10)
            if verify_audit_rate is None else verify_audit_rate)
        self.verify_audit_rate = min(max(float(self.verify_audit_rate), 0.0), 1.0)

        # Domain Glossary Manager
        self.glossary = AcademicGlossaryManager()
        self.paper_direction = ""
        self._history: list[dict] = []  # [{en, zh}]
        self.stats = self._new_stats()

        # Check model type and initialize special tokens
        self._is_hunyuan = self._check_hunyuan()
        if self._is_hunyuan:
            # Hunyuan MT special tokens
            self.tok_bos = self.llm.detokenize([120000])  # <｜hy_begin of sentence｜>
            self.tok_eos = self.llm.detokenize([120020])  # <｜hy_placeholder no 2｜>
            self.tok_p3  = self.llm.detokenize([120021])  # <｜hy_placeholder no 3｜>
            self.tok_usr = self.llm.detokenize([120006])  # <｜hy_User｜>
            self.tok_ast = self.llm.detokenize([120007])  # <｜hy_Assistant｜>
            print("  [Translator] Initialized with Hunyuan-MT Native ChatML & Dynamic Constraints.")
        else:
            print("  [Translator] Initialized with Generic Fallback Prompt Template.")

    def _check_hunyuan(self) -> bool:
        """Check if model uses Hunyuan tokenizer vocabulary."""
        tmpl = getattr(self.llm, "_chat_template", "").lower()
        if "hy_" in tmpl or "hunyuan" in tmpl:
            return True
        if hasattr(self.llm, "eos_token") and self.llm.eos_token == 120020:
            return True
        return False

    # ── Public API ──

    def set_direction_from_abstract(self, abstract_en: str):
        """Extract domain taxonomy and paper-specific terminology from abstract."""
        # 1. Analyze domain taxonomy and extract novel abbreviations/terms dynamically
        self.glossary.analyze_paper(abstract_en)
        domain_zh = self.glossary.detected_domain

        # 2. Extract direction keywords from abstract
        if self._is_hunyuan:
            prompt = (f"{self.tok_bos}提取以下学术论文摘要的核心研究领域关键词，用·连接，不超过15字。只输出关键词。{self.tok_p3}"
                      f"{self.tok_usr}{abstract_en[:1500]}{self.tok_ast}")
        else:
            prompt = DIRECTION_PROMPT.format(abstract=abstract_en[:1500])

        output = self.llm.generate(prompt, max_tokens=64, temperature=0.3)
        direction = self._clean(output)
        if direction and 2 < len(direction) < 30:
            self.paper_direction = f"{domain_zh}·{direction}"
        else:
            self.paper_direction = f"{domain_zh}·学术论文翻译"

        print(f"  [Direction] {self.paper_direction}")
        if self.glossary.paper_specific_terms:
            terms_preview = list(self.glossary.paper_specific_terms.keys())[:8]
            print(f"  [Dynamic Terms] Injected {len(self.glossary.paper_specific_terms)} novel terms: {terms_preview}")

    @staticmethod
    def _mask_entities(text: str) -> tuple[str, dict]:
        """
        Mask math expressions, citations, and URLs with Unicode tokens (⟪M0⟫, ⟪R0⟫, ⟪U0⟫)
        which MT tokenizers treat as atomic and never split or hallucinate.
        """
        masks = {}

        # 1. URLs
        def _mask_url(m):
            key = f"⟪U{len(masks)}⟫"
            masks[key] = m.group(0)
            return key
        text = re.sub(r'https?://[^\s)\]]+', _mask_url, text)

        # 2. Display and inline math $$...$$, $...$, \(...\), \[...\]
        def _mask_math(m):
            key = f"⟪M{len(masks)}⟫"
            masks[key] = m.group(0)
            return key
        text = re.sub(r'\$\$[\s\S]+?\$\$', _mask_math, text)
        text = re.sub(r'\$[^\$\n]+?\$', _mask_math, text)
        text = re.sub(r'\\\[[\s\S]+?\\\]', _mask_math, text)
        text = re.sub(r'\\\([^\n]+?\\\)', _mask_math, text)

        # 3. Reference citations [1], [1, 2], [1-3]
        def _mask_ref(m):
            key = f"⟪R{len(masks)}⟫"
            masks[key] = m.group(0)
            return key
        text = re.sub(r'\[\s*\d+(?:[\s,\-–—]+\d+)*\s*\]', _mask_ref, text)

        return text, masks

    @staticmethod
    def _unmask_entities(text: str, masks: dict) -> str:
        """Restore masked placeholders accurately with fuzzy regex fallback."""
        if not masks or not text:
            return text
        for key, val in masks.items():
            if key in text:
                text = text.replace(key, val)
            else:
                # Fuzzy fallback: e.g. ⟪M0⟫ was outputted as ⟪M 0⟫, 《M0》, ⟦M0⟧, or [M0]
                m = re.match(r'⟪([MRU])(\d+)⟫', key)
                if m:
                    k_type, k_num = m.group(1), m.group(2)
                    fuzzy_pattern = rf'[⟪《⟦\[(]\s*{k_type}\s*{k_num}\s*[⟫》⟧\])]'
                    text = re.sub(fuzzy_pattern, lambda _: val, text, flags=re.IGNORECASE)
        return text

    def translate_block(self, text: str, block_type: str = 'text') -> str | None:
        """
        Translate a single block. Returns None if block should be skipped.
        """
        # Title → skip (Rule: Title passthrough)
        if block_type == 'title':
            self.stats['skipped'] += 1
            return None

        # Pseudo-title detection
        if block_type == 'text' and is_pseudo_title(text, block_type):
            self.stats['skipped'] += 1
            return None

        # Mask math/refs/urls
        masked_text, masks = self._mask_entities(text)
        text_len = len(masked_text)

        was_chunked = False

        # Short text
        if text_len < 200:
            zh = self._translate_short(masked_text)
        # Long text → chunk with overlap + per-chunk verification
        elif text_len > self.chunk_size:
            zh = self._translate_long(masked_text)
            was_chunked = True
        # Normal text → translate with context & dynamic constraints
        else:
            zh = self._translate_normal(masked_text)

        # Restore original formulas and references
        zh = self._unmask_entities(zh, masks)

        # Apply post-correction for academic terminology and MT artifacts
        zh = self.glossary.post_correct(zh, text)

        # Quality Gate (for non-chunked blocks; chunked blocks verify inside _translate_long)
        if not was_chunked:
            zh = self._verify_or_retry(text, zh)

        # Update history for context window (skip error strings)
        if zh and not zh.startswith('[ERROR'):
            self._history.append({'en': text, 'zh': zh})
            if len(self._history) > 10:
                self._history = self._history[-10:]

        return zh

    def reset(self):
        self._history = []
        self.paper_direction = ""
        self.glossary = AcademicGlossaryManager()
        self.stats = self._new_stats()

    # ── Prompt Construction & Generation ──

    def _build_system_message(self, text: str) -> str:
        """Build dynamic system message with relevant term constraints."""
        sys_msg = BASE_ACADEMIC_SYSTEM_PROMPT
        if self.paper_direction:
            sys_msg = f"【论文研究方向】{self.paper_direction}\n" + sys_msg

        # Dynamic query-relevant constraint injection (< 25 tokens)
        constraints = self.glossary.get_relevant_constraints(text)
        if constraints:
            sys_msg += f"\n{constraints}"
        return sys_msg

    def _translate_short(self, text: str) -> str:
        sys_msg = self._build_system_message(text)
        if self._is_hunyuan:
            prompt = f"{self.tok_bos}{sys_msg}{self.tok_p3}{self.tok_usr}{text}{self.tok_ast}"
        else:
            prompt = SHORT_PROMPT.format(direction=self.paper_direction, style=sys_msg, text=text)
        return self._gen(prompt, max_tokens=160, temp=0.3)

    def _translate_normal(self, text: str, prev_en: str = None, prev_zh: str = None,
                          temperature: float = 0.3) -> str:
        sys_msg = self._build_system_message(text)

        # Context: either explicit prev_en/prev_zh or latest from history
        if not prev_en and self._history:
            ctx = self._history[-1]
            if len(ctx['en']) > 20:
                prev_en = ctx['en']
                prev_zh = ctx['zh']

        if self._is_hunyuan:
            if prev_en and prev_zh and len(prev_en) > 20:
                # Multi-turn few-shot context
                prompt = (f"{self.tok_bos}{sys_msg}{self.tok_p3}"
                          f"{self.tok_usr}{prev_en[:260]}{self.tok_ast}{prev_zh[:260]}{self.tok_eos}"
                          f"{self.tok_usr}{text}{self.tok_ast}")
            else:
                prompt = f"{self.tok_bos}{sys_msg}{self.tok_p3}{self.tok_usr}{text}{self.tok_ast}"
        else:
            if prev_en and prev_zh and len(prev_en) > 20:
                prompt = CONTEXT_PROMPT.format(
                    direction=self.paper_direction, style=sys_msg,
                    prev_en=prev_en[:260], prev_zh=prev_zh[:260], text=text)
            else:
                prompt = NORMAL_PROMPT.format(
                    direction=self.paper_direction, style=sys_msg, text=text)

        return self._gen(prompt, max_tokens=512, temp=temperature)

    def _translate_long(self, text: str) -> str:
        """Split long text into sentence-grouped chunks with sliding 1-sentence overlap."""
        chunks = self._split_chunks(text)
        if len(chunks) <= 1:
            return self._translate_normal(text)

        results = []
        prev_chunk_en = None
        prev_chunk_zh = None

        for chunk in chunks:
            prev_en_ctx = None
            prev_zh_ctx = None
            if prev_chunk_en and prev_chunk_zh:
                # Extract last sentence of previous chunk for semantic continuity
                s_en = re.split(r'(?<=[.!?])\s+', prev_chunk_en.strip())
                s_zh = re.split(r'(?<=[。！？])', prev_chunk_zh.strip())
                if s_en and s_zh:
                    prev_en_ctx = s_en[-1]
                    prev_zh_ctx = s_zh[-1]

            zh = self._translate_normal(chunk, prev_en=prev_en_ctx, prev_zh=prev_zh_ctx)
            verified_zh = self._verify_or_retry(chunk, zh)
            results.append(verified_zh)
            prev_chunk_en = chunk
            prev_chunk_zh = verified_zh

        return ''.join(results)

    # ── Quality Gate & Back-Translation Verification ──

    @staticmethod
    def _new_stats() -> dict:
        return {
            'total': 0, 'skipped': 0, 'passed': 0, 'retried': 0, 'failed': 0,
            'fast_accepted': 0, 'fast_audited': 0, 'fast_rejected': 0,
            'back_verified': 0,
        }

    def _verify_or_retry(self, en: str, zh: str) -> str:
        """Multi-dimensional Quality Gate: structure, numbers, polarity, and back-translation."""
        self.stats['total'] += 1
        if not self.verify or len(en) <= 40:
            self.stats['passed'] += 1
            return zh

        if self.verify_strategy == 'adaptive':
            accepted, _reason = self._passes_fast_gate(en, zh)
            if accepted and not self._should_audit(en):
                self.stats['fast_accepted'] += 1
                self.stats['passed'] += 1
                return zh
            if accepted:
                self.stats['fast_audited'] += 1
            else:
                self.stats['fast_rejected'] += 1

        self.stats['back_verified'] += 1
        if self._verify(en, zh):
            self.stats['passed'] += 1
            return zh

        # First verify failed: retry at lower temperature with post-correction
        from config import get as cfg
        retry_temp = cfg('sampling', 'retry_temperature', default=0.1)
        zh2 = self._translate_normal(en, temperature=retry_temp)
        zh2 = self.glossary.post_correct(zh2, en)

        self.stats['back_verified'] += 1
        if self._verify(en, zh2):
            self.stats['retried'] += 1
            return zh2

        self.stats['failed'] += 1
        return zh2 if len(zh2) >= len(zh) * 0.7 else zh

    def _should_audit(self, en: str) -> bool:
        """Deterministic sampling of safe candidates for full verification audit."""
        if self.verify_audit_rate <= 0:
            return False
        if self.verify_audit_rate >= 1:
            return True
        bucket = int(hashlib.sha256(en.encode('utf-8')).hexdigest()[:8], 16) % 10_000
        return bucket < round(self.verify_audit_rate * 10_000)

    @staticmethod
    def _passes_fast_gate(en: str, zh: str) -> tuple[bool, str]:
        """
        Fast gate: validates structure, completeness, numerical invariance,
        and logical polarity before bypassing back-translation.
        """
        en, zh = en.strip(), zh.strip()
        if not zh or zh.startswith('[ERROR'):
            return False, 'empty_or_error'
        if re.search(r'(?i)^(english|chinese|translation|analysis)\s*[:：]', zh):
            return False, 'label_leak'
        if len(en) < 40:
            return True, 'short_source_ok'

        zh_clean = re.sub(r'\s+', '', zh)
        en_clean = re.sub(r'\s+', '', en)
        ratio = len(zh_clean) / max(len(en_clean), 1)
        if not (0.20 <= ratio <= 1.50):
            return False, 'length_ratio'

        chinese_chars = len(re.findall(r'[\u3400-\u9fff]', zh))
        if chinese_chars < 6 or chinese_chars / max(len(zh_clean), 1) < 0.20:
            return False, 'insufficient_chinese'

        if re.search(r'(.{8,30})\1{2,}', zh):
            return False, 'repetition'

        # 1. Numerical Invariance Check: key numbers, percentages, decimals must be preserved
        numbers_en = set(re.findall(r'\b\d+(?:\.\d+)?%?\b', en))
        salient_numbers = {n for n in numbers_en if len(n) > 1 or '.' in n or '%' in n}
        for num in salient_numbers:
            if num not in zh_clean:
                return False, f'number_missing_{num}'

        # 2. Polarity Invariance Check: English negative polarity must yield Chinese negative words
        neg_en = bool(re.search(r'\b(not|never|no longer|neither|nor|fails? to|failed to)\b', en, re.I))
        neg_zh = bool(re.search(r'[不未无非零绝]', zh))
        if neg_en and not neg_zh:
            return False, 'negation_missing'

        # 3. Unicode Mask Preservation
        masks_en = re.findall(r'⟪[MRU]\d+⟫', en)
        for m in masks_en:
            if m not in zh:
                return False, f'mask_missing_{m}'

        return True, 'accepted'

    def _verify(self, en: str, zh: str) -> bool:
        back = self._back_translate(zh)
        if not back:
            return False
        sim = self._similarity(en, back)
        from config import get as cfg
        length = len(en)
        if length < 100: threshold = cfg('verify', 'threshold_short', default=0.50)
        elif length < 300: threshold = cfg('verify', 'threshold_medium', default=0.45)
        elif length < 600: threshold = cfg('verify', 'threshold_long', default=0.40)
        else: threshold = cfg('verify', 'threshold_xlong', default=0.35)
        return sim >= threshold

    def _back_translate(self, zh: str) -> str:
        if self._is_hunyuan:
            prompt = (f"{self.tok_bos}将以下中文学术论文文本准确翻译为英文：{self.tok_p3}"
                      f"{self.tok_usr}{zh}{self.tok_ast}")
        else:
            prompt = BACK_PROMPT.format(source=zh)
        return self._gen(prompt, max_tokens=256, temp=0.2)

    @staticmethod
    def _similarity(a: str, b: str) -> float:
        a, b = a.lower().strip(), b.lower().strip()
        if not a or not b: return 0.0
        a_t, b_t = set(a.split()), set(b.split())
        ts = len(a_t & b_t) / max(len(a_t), len(b_t)) if a_t else 0.0
        def ng(s, n=3):
            s = '  ' + s + '  '
            return {s[i:i+n] for i in range(len(s)-n+1)}
        a_n, b_n = ng(a.replace('-',' ')), ng(b.replace('-',' '))
        cs = len(a_n & b_n) / max(len(a_n), len(b_n)) if a_n else 0.0
        return 0.6 * ts + 0.4 * cs

    # ── Helpers ──

    def _split_chunks(self, text: str) -> list[str]:
        """Split text at sentence boundaries into chunks ≤ chunk_size."""
        sentences = re.split(r'(?<=[.!?])\s+(?=[A-Z])', text)
        sentences = [s.strip() for s in sentences if s.strip()]
        if not sentences: return [text]

        chunks, cur, cur_len = [], [], 0
        for s in sentences:
            if cur_len + len(s) > self.chunk_size and cur:
                chunks.append(' '.join(cur))
                cur, cur_len = [], 0
            cur.append(s)
            cur_len += len(s)
        if cur: chunks.append(' '.join(cur))
        return chunks

    def _gen(self, prompt: str, max_tokens: int, temp: float) -> str:
        from config import get as cfg
        output = self.llm.generate(prompt, max_tokens=max_tokens,
                                   temperature=temp,
                                   top_p=cfg('sampling', 'top_p', default=0.6),
                                   top_k=cfg('sampling', 'top_k', default=20))
        return self._clean(output)

    @staticmethod
    def _clean(output: str) -> str:
        """Clean output text, strip markdown code blocks and MT conversational prefixes."""
        # Strip code blocks if any
        if output.startswith('```') and output.endswith('```'):
            lines = output.split('\n')[1:-1]
            output = '\n'.join(lines)

        lines = output.split('\n')
        result = []
        for line in lines:
            line = line.strip()
            if not line:
                if result: break
                continue
            if line.startswith(('English:', 'Source:', 'Original:')) and result: break
            if line.startswith(('Chinese:', 'Translation:', '中文：', '翻译：')):
                line = re.sub(r'^(?:Chinese|Translation|中文|翻译)\s*[:：]\s*', '', line)
            if line and not line.startswith('---') and not line.startswith('Summary:'):
                result.append(line)
        return ' '.join(result).strip()

    def close(self):
        self.llm.close()
