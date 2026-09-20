"""
OvisOCR2 Markdown AST & Semantic Block Parser
Converts end-to-end Markdown output from OvisOCR2 into LunePaper's standardized block structure:
- '# Header' -> type: 'title', passthrough: True (NEVER translated, user core rule)
- '$$ ... $$' -> type: 'equation', passthrough: True (with \tag{...} label fusion)
- '<table ... </table>' -> type: 'table', passthrough: True
- '<img src="images/bbox_l_t_r_b.jpg" />' -> type: 'image', bbox: [l, t, r, b]
- 'Figure X: ...' -> type: 'image_caption'
- '[1] Author ...' -> type: 'ref_text', passthrough: True
- Page numbers ('2', '3', 'Page 4') -> type: 'page_number', passthrough: True (filtered in worker)
- Normal paragraphs -> type: 'text', passthrough: False
"""

import re
from typing import List, Dict, Any


def clean_latex_math(text: str) -> str:
    """Fix common Ovis tokenization spacing artifacts in LaTeX equations."""
    if not text:
        return text
    text = text.replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>')
    # Standard trigonometric / math functions with spaced chars
    text = re.sub(r'\bs\s+i\s+n\b', r'\\sin', text)
    text = re.sub(r'\bc\s+o\s+s\b', r'\\cos', text)
    text = re.sub(r'\bt\s+a\s+n\b', r'\\tan', text)
    text = re.sub(r'\bl\s+o\s+g\b', r'\\log', text)
    text = re.sub(r'\be\s+x\s+p\b', r'\\exp', text)
    text = re.sub(r'\bm\s+a\s+x\b', r'\\max', text)
    text = re.sub(r'\bm\s+i\s+n\b', r'\\min', text)

    # Common variable / identifier character spacing
    text = re.sub(r'\bP\s+E\b', 'PE', text)
    text = re.sub(r'\bp\s+o\s+s\b', 'pos', text)
    text = re.sub(r'\bm\s+o\s+d\s+e\s+l\b', 'model', text)
    text = re.sub(r'\bl\s+r\s+a\s+t\s+e\b', 'lrate', text)
    text = re.sub(r'\bs\s+t\s+e\s+p\b', 'step', text)
    text = re.sub(r'\bw\s+a\s+r\s+m\s+u\s+p\b', 'warmup', text)
    # Fix escaped underscores followed by spaces, e.g. step\_{n} u m -> step_{\mathrm{num}}
    text = re.sub(r'\\_\{n\}\s*u\s*m\b', r'_{\\mathrm{num}}', text)
    text = re.sub(r'\\_\{s\}\s*t\s*e\s*p\s*s\b', r'_{\\mathrm{steps}}', text)
    # Fix subscript grouping without braces: _\mathrm{foo} -> _{\mathrm{foo}}
    text = re.sub(r'_\\mathrm\{([^{}]+)\}', r'_{\\mathrm{\1}}', text)
    text = re.sub(r'_\\text\{([^{}]+)\}', r'_{\\text{\1}}', text)
    # Fix spaced decimals: -0. 5 -> -0.5, 88. 3 -> 88.3
    text = re.sub(r'(\d+)\.\s+(\d+)', r'\1.\2', text)
    text = re.sub(r'\\\\\s*where\b', r'\\\\ \\text{where }', text)
    text = re.sub(r'\.\s*\.\s*\.', r'\\dots', text)
    return text


def parse_ovis_markdown(raw_text: str) -> List[Dict[str, Any]]:
    """
    Parse raw OvisOCR2 output into structured LunePaper blocks.
    
    Returns:
        List of dicts:
        [
            {
                'type': 'title' | 'text' | 'equation' | 'table' | 'image' | 'ref_text' | 'image_caption' | 'page_number',
                'bbox': [x1, y1, x2, y2] (for image) or [],
                'text': str,
                'passthrough': bool
            },
            ...
        ]
    """
    if not raw_text or not raw_text.strip():
        return []

    # 1. Strip think blocks if present
    text = re.sub(r'<think>[\s\S]*?</think>', '', raw_text).strip()

    # Pre-clean inline equation tags: $$ ... $$ (1) -> $$\n... \tag{1}\n$$
    def _tag_inline_repl(m):
        inner = m.group(1).strip()
        if inner.startswith('$$'):
            inner = inner[2:].strip()
        tag_val = m.group(2)
        return f"\n\n$$\n{inner} \\tag{{{tag_val}}}\n$$\n\n"

    text = re.sub(
        r'\$\$([\s\S]*?)\$\$\s*\(([0-9]+[a-z]?|[0-9]+\.[0-9]+|[A-Z]\.?[0-9]+)\)',
        _tag_inline_repl,
        text
    )

    # 2. Tokenize atomic multiline blocks (HTML tables, display equations, img tags)
    placeholders = {}
    p_counter = 0

    def _replace_with_placeholder(match, btype, passthrough=True, extra=None):
        nonlocal p_counter
        pid = f"__BLOCK_PLACEHOLDER_{p_counter}__"
        p_counter += 1
        block_data = {
            'type': btype,
            'bbox': extra.get('bbox', []) if extra else [],
            'text': match.group(0).strip(),
            'passthrough': passthrough
        }
        if extra:
            block_data.update(extra)
        placeholders[pid] = block_data
        return f"\n\n{pid}\n\n"

    # 2a. Image tags with bbox coordinates: <img src="images/bbox_180_96_823_405.jpg" />
    def _img_repl(m):
        raw_tag = m.group(0)
        # Try standard underscore format: bbox_l_t_r_b
        m_coords = re.search(r'bbox_(\d+)_(\d+)_(\d+)_(\d+)', raw_tag)
        if m_coords:
            bbox = [int(m_coords.group(i)) for i in range(1, 5)]
        else:
            # Fallback for 12-digit concatenated bbox (3 digits per coord)
            m_12 = re.search(r'bbox_(\d{3})(\d{3})(\d{3})(\d{3})', raw_tag)
            if m_12:
                bbox = [int(m_12.group(i)) for i in range(1, 5)]
            else:
                bbox = []

        return _replace_with_placeholder(
            m, 'image', passthrough=True,
            extra={'bbox': bbox, 'text': ''}
        )

    text = re.sub(r'<img\s+src="[^"]*images/bbox_[^"]*"\s*/>', _img_repl, text, flags=re.IGNORECASE)

    # 2b. HTML Tables: <table ... </table>
    def _table_repl(m):
        return _replace_with_placeholder(m, 'table', passthrough=True, extra={'text': m.group(0).strip()})

    text = re.sub(r'<table[\s\S]*?</table>', _table_repl, text, flags=re.IGNORECASE)

    # 2c. Display LaTeX Equations: $$ ... $$ or \[ ... \]
    def _eq_repl(m):
        raw = m.group(0).strip()
        if raw.startswith(r'\['):
            raw = raw[2:-2].strip()
        elif raw.startswith('$$') and raw.endswith('$$'):
            raw = raw[2:-2].strip()
        raw = clean_latex_math(raw)
        formatted_eq = f"$$\n{raw}\n$$"
        return _replace_with_placeholder(m, 'equation', passthrough=True, extra={'text': formatted_eq})

    text = re.sub(r'\$\$[\s\S]*?\$\$', _eq_repl, text)
    text = re.sub(r'\\\[[\s\S]*?\\\]', _eq_repl, text)

    # 3. Split by paragraph boundaries (two or more newlines)
    raw_paragraphs = [p.strip() for p in re.split(r'\n{2,}', text) if p.strip()]

    blocks = []
    in_references = False

    # Regex patterns
    RE_HEADING = re.compile(r'^(#{1,6})\s+(.+)$', re.DOTALL)
    RE_REF_HEADING = re.compile(r'^(#{1,6})\s*(?:\d+\.?\s*)?(?:references|bibliography|参考文献)', re.IGNORECASE)
    RE_REF_ITEM = re.compile(r'^\[\d+\]\s+')
    RE_CAPTION = re.compile(r'^(?:Figure|Fig\.|Table|Tab\.)\s+\d+[:\.]\s*', re.IGNORECASE)
    RE_PAGE_NUMBER = re.compile(
        r'^[-—–\s]*(?:page\s+)?(?:\d{1,4}|[ivxlc]+)(?:\s*(?:of|/)\s*(?:\d{1,4}|[ivxlc]+))?[-—–\s]*$',
        re.IGNORECASE
    )
    RE_EQ_LABEL = re.compile(r'^\s*\((\d+[a-z]?|\d+\.\d+|[A-Z]\.?\d+)\)\s*$')

    def _create_block(t: str) -> Dict[str, Any]:
        nonlocal in_references
        t = t.strip()
        if RE_PAGE_NUMBER.match(t):
            return {
                'type': 'page_number',
                'bbox': [],
                'text': t,
                'passthrough': True
            }
        if RE_EQ_LABEL.match(t):
            return {
                'type': 'equation_label',
                'bbox': [],
                'text': t,
                'passthrough': True
            }
        if in_references or RE_REF_ITEM.match(t):
            return {
                'type': 'ref_text',
                'bbox': [],
                'text': t,
                'passthrough': True
            }
        if RE_CAPTION.match(t):
            return {
                'type': 'image_caption',
                'bbox': [],
                'text': t,
                'passthrough': False  # Captions are translated
            }
        return {
            'type': 'text',
            'bbox': [],
            'text': t,
            'passthrough': False
        }

    for p in raw_paragraphs:
        # Check if this paragraph is an atomic placeholder
        if p in placeholders:
            blocks.append(placeholders[p])
            continue

        # Check for Markdown Pipe Table
        lines = [line.strip() for line in p.split('\n') if line.strip()]
        if len(lines) >= 2 and all(l.startswith('|') and l.endswith('|') for l in lines):
            if any('---' in l for l in lines):
                blocks.append({
                    'type': 'table',
                    'bbox': [],
                    'text': p,
                    'passthrough': True
                })
                continue

        # Check if single or multi-line heading
        m_head = RE_HEADING.match(p)
        if m_head:
            heading_content = m_head.group(2).strip()
            # If this is the references section heading
            if RE_REF_HEADING.match(p):
                in_references = True

            # STRICT NON-NEGOTIABLE RULE: Headings must NOT be translated!
            blocks.append({
                'type': 'title',
                'bbox': [],
                'text': heading_content,
                'passthrough': True
            })
            continue

        # Check if paragraph contains lines starting with headings or references mixed together
        if '\n' in p:
            split_sublines = p.split('\n')
            has_embedded_heading = any(RE_HEADING.match(l.strip()) for l in split_sublines)
            if has_embedded_heading:
                curr_text_lines = []
                for l in split_sublines:
                    l_clean = l.strip()
                    if not l_clean:
                        continue
                    m_subhead = RE_HEADING.match(l_clean)
                    if m_subhead:
                        if curr_text_lines:
                            blocks.append(_create_block(' '.join(curr_text_lines)))
                            curr_text_lines = []
                        if RE_REF_HEADING.match(l_clean):
                            in_references = True
                        blocks.append({
                            'type': 'title',
                            'bbox': [],
                            'text': m_subhead.group(2).strip(),
                            'passthrough': True
                        })
                    else:
                        curr_text_lines.append(l_clean)
                if curr_text_lines:
                    blocks.append(_create_block(' '.join(curr_text_lines)))
                continue

        # Normal single block
        blocks.append(_create_block(p))

    # 4. Equation Tag Fusion Pass
    # Fuses orphan equation labels like (1), (2), (3) into preceding equation blocks via \tag{...}
    merged_blocks = []
    i = 0
    while i < len(blocks):
        curr = blocks[i]
        if (curr.get('type') == 'equation' and 
            i + 1 < len(blocks) and 
            blocks[i+1].get('type') in ('equation_label', 'text', 'ref_text', 'page_number')):
            next_txt = blocks[i+1].get('text', '').strip()
            m_tag = RE_EQ_LABEL.match(next_txt)
            if m_tag:
                tag_val = m_tag.group(1)
                eq_txt = curr.get('text', '').strip()
                if eq_txt.endswith('$$') and r'\tag{' not in eq_txt:
                    inner = eq_txt[:-2].strip()
                    if inner.startswith('$$'):
                        inner = inner[2:].strip()
                    curr['text'] = f"$$\n{inner} \\tag{{{tag_val}}}\n$$"
                    merged_blocks.append(curr)
                    i += 2  # Absorb and skip the orphan label block
                    continue
        if curr.get('type') == 'equation_label':
            # Unabsorbed orphan label (skip to prevent junk translation)
            i += 1
            continue
        merged_blocks.append(curr)
        i += 1

    return merged_blocks
