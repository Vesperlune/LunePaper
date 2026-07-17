"""
Phase 5: Smart Translator
  - Pseudo-title detection (skip short/likely-heading text)
  - OCR block merging (rejoin split paragraphs)
  - Abstract direction extraction
  - Long text chunking + sliding context window
  - Back-translation verification
"""
import os, sys, re
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from infer.llama_binding import LlamaModel

# ── Prompts (中文指令 + 学术风格约束) ──

STYLE_RULES = """【翻译要求】
1. 风格严谨、客观、简洁，符合中文学术论文写作规范
2. 术语使用学术界标准译法，同一术语全文保持统一
3. 保持原文因果、转折、递进等逻辑关系
4. 中文表达自然流畅，避免生硬直译
5. 公式 \\(...\\) 和 \\[...\\] 原样保留
6. 引用标记 [1]、[Smith 2024] 等原样保留
7. 数字、百分比、数值、单位原样保留
8. 缩写 LLM、KV、OCR、GPU、MHA、SWA 等不翻译
9. 模型名、人名、机构名保留英文
【禁止】
不添加原文没有的内容，不省略信息，不解释或评价翻译内容"""

DIRECTION_PROMPT = """根据以下学术论文摘要，用一句简短中文总结其主要研究领域和关键主题。只输出总结：

{abstract}

总结："""

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

    # 1. Very short → likely a heading
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
            if not text.rstrip().endswith(('.', '?', '!', '."', '.)')):
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
    # Bbox vertical proximity
    if 'bbox' in prev and 'bbox' in cur:
        prev_bottom = prev['bbox'][3]
        cur_top = cur['bbox'][1]
        line_h = max(prev['bbox'][3] - prev['bbox'][1], 10)
        if cur_top - prev_bottom > line_h * 2.5:
            return False


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

        # Find last text block on current page
        last_text = None
        for j in range(len(cur_page) - 1, -1, -1):
            if cur_page[j].get('type') == 'text':
                last_text = cur_page[j]
                break
        if last_text is None:
            continue

        # Find first text block on next page
        first_text = None
        for j in range(len(next_page)):
            if next_page[j].get('type') == 'text':
                first_text = next_page[j]
                break
        if first_text is None:
            continue

        # Check continuation conditions
        pt = last_text['en'].rstrip() if last_text.get('en') else last_text['text'].rstrip()
        ct = first_text['en'].lstrip() if first_text.get('en') else first_text['text'].lstrip()
        if not pt or not ct:
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
    Tries to split at sentence boundaries; falls back to proportional split.
    Returns (zh_part1, zh_part2).
    """
    total = part1_len + part2_len
    if total == 0:
        return combined_zh, ''

    # Try splitting at sentence boundaries (Chinese punctuation)
    sentences = re.split(r'(?<=[。！？；\n])', combined_zh)
    sentences = [s for s in sentences if s.strip()]

    if len(sentences) >= 2:
        ratio = part1_len / total
        target_chars = int(len(combined_zh) * ratio)
        accumulated = 0
        for k, s in enumerate(sentences):
            accumulated += len(s)
            if accumulated >= target_chars:
                zh1 = ''.join(sentences[:k+1])
                zh2 = ''.join(sentences[k+1:])
                return zh1, zh2

    # Fallback: proportional split
    split_pos = int(len(combined_zh) * ratio)
    return combined_zh[:split_pos], combined_zh[split_pos:]


# ═══════════════════════════════════════════════
# SmartTranslator
# ═══════════════════════════════════════════════

class SmartTranslator:
    """Phase 5 translator with direction guidance, chunking, and verification."""

    def __init__(self, model_path: str = None, n_gpu_layers: int = 99,
                 verify: bool = True, chunk_size: int = None):
        from config import get as cfg
        if model_path is None:
            model_path = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                cfg('models', 'translation', default='Hy-MT2-1.8B-Q8_0.gguf'))
        self.llm = LlamaModel(model_path, n_gpu_layers=n_gpu_layers,
                              n_ctx=cfg('translation', 'n_ctx', default=4096),
                              n_threads=cfg('translation', 'n_threads', default=4))
        self.verify = verify
        self.chunk_size = chunk_size or cfg('translation', 'chunk_size', default=500)
        self.paper_direction = ""
        self._history: list[dict] = []  # [{en, zh}]
        self.stats = {'total': 0, 'skipped': 0, 'passed': 0, 'retried': 0, 'failed': 0}

    # ── Public API ──

    def set_direction_from_abstract(self, abstract_en: str):
        """Extract paper direction from the abstract text."""
        prompt = DIRECTION_PROMPT.format(abstract=abstract_en[:1500])
        output = self.llm.generate(prompt, max_tokens=64, temperature=0.3)
        direction = self._clean(output)
        if direction and len(direction) > 3:
            self.paper_direction = direction
            print(f"  [Direction] {direction}")
        else:
            self.paper_direction = "学术论文翻译"

    def translate_block(self, text: str, block_type: str = 'text') -> str | None:
        """
        Translate a single block. Returns None if block should be skipped.
        """
        # Title → skip
        if block_type == 'title':
            self.stats['skipped'] += 1
            return None

        # Pseudo-title detection
        if block_type == 'text' and is_pseudo_title(text, block_type):
            self.stats['skipped'] += 1
            return None

        self.stats['total'] += 1
        text_len = len(text)

        was_chunked = False

        # Short text → direct translate
        if text_len < 200:
            zh = self._translate_short(text)
        # Long text → chunk + per-chunk verification inside _translate_long
        elif text_len > self.chunk_size:
            zh = self._translate_long(text)
            was_chunked = True
        # Normal text → translate with direction
        else:
            zh = self._translate_normal(text)

        # Back-translation verification (skip for chunked texts: verified per-chunk)
        if self.verify and text_len > 40 and not was_chunked:
            if not self._verify(text, zh):
                from config import get as cfg
                zh2 = self._translate_normal(text, temperature=cfg('sampling', 'retry_temperature', default=0.2))
                if self._verify(text, zh2):
                    zh = zh2
                    self.stats['retried'] += 1
                else:
                    self.stats['failed'] += 1
                    return zh  # keep original despite low score
            else:
                self.stats['passed'] += 1
        else:
            self.stats['passed'] += 1

        # Update history for context window
        self._history.append({'en': text, 'zh': zh})
        if len(self._history) > 10:
            self._history = self._history[-10:]

        return zh

    def reset(self):
        self._history = []
        self.paper_direction = ""
        self.stats = {'total': 0, 'skipped': 0, 'passed': 0, 'retried': 0, 'failed': 0}

    # ── Translation methods ──

    def _translate_short(self, text: str) -> str:
        prompt = SHORT_PROMPT.format(direction=self.paper_direction, style=STYLE_RULES, text=text)
        return self._gen(prompt, max_tokens=128, temp=0.4)

    def _translate_normal(self, text: str, temperature: float = 0.5) -> str:
        # Use context window if available
        ctx = self._history[-1] if self._history else None
        if ctx and len(ctx['en']) > 30:
            prompt = CONTEXT_PROMPT.format(
                direction=self.paper_direction, style=STYLE_RULES,
                prev_en=ctx['en'][:300],
                prev_zh=ctx['zh'][:300],
                text=text)
        else:
            prompt = NORMAL_PROMPT.format(direction=self.paper_direction, style=STYLE_RULES, text=text)
        return self._gen(prompt, max_tokens=512, temp=temperature)

    def _translate_long(self, text: str) -> str:
        """Split long text, translate each chunk with context + per-chunk verification."""
        chunks = self._split_chunks(text)
        if len(chunks) <= 1:
            return self._translate_normal(text)

        results = []
        for chunk in chunks:
            zh = self._translate_normal(chunk)
            # Per-chunk verification (not just at the end)
            if self.verify and len(chunk) > 40:
                if not self._verify(chunk, zh):
                    # Retry this chunk with lower temperature
                    zh2 = self._translate_normal(chunk, temperature=0.2)
                    if self._verify(chunk, zh2):
                        zh = zh2
            results.append(zh)
        return ' '.join(results)

    # ── Back-translation verification ──

    def _verify(self, en: str, zh: str) -> bool:
        back = self._back_translate(zh)
        if not back:
            return True
        sim = self._similarity(en, back)
        # Adaptive threshold from config
        from config import get as cfg
        length = len(en)
        if length < 100: threshold = cfg('verify', 'threshold_short', default=0.50)
        elif length < 300: threshold = cfg('verify', 'threshold_medium', default=0.45)
        elif length < 600: threshold = cfg('verify', 'threshold_long', default=0.40)
        else: threshold = cfg('verify', 'threshold_xlong', default=0.35)
        return sim >= threshold

    def _back_translate(self, zh: str) -> str:
        prompt = BACK_PROMPT.format(source=zh)
        return self._gen(prompt, max_tokens=256, temp=0.3)

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
        lines = output.split('\n')
        result = []
        for line in lines:
            line = line.strip()
            if not line:
                if result: break      # stop at empty line only AFTER content
                continue               # skip leading empty lines
            if line.startswith('English:') and result: break
            if line.startswith('Chinese:'): line = line[len('Chinese:'):].strip()
            if line and not line.startswith('---') and not line.startswith('Summary:'):
                result.append(line)
        return ' '.join(result).strip()

    def close(self):
        self.llm.close()
