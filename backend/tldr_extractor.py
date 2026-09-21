"""
Paper TL;DR Extractor
Extracts 4-dimensional structured overview (Background, Method, Metrics, Conclusion)
from paper translation blocks or raw abstract text.
Zero external dependencies, robust heuristic fallback, and LLM-compatible format.
"""
import re
from typing import Optional


def locate_abstract_text(blocks: list) -> str:
    """
    Locate Chinese translated abstract from a list of document blocks.
    Tries multiple strategies:
    1. Explicit block with type == 'abstract'
    2. Block following a title/header containing 'abstract' or '摘要'
    3. Block starting with '摘要' or '【摘要】'
    4. Largest narrative text block on the first page
    """
    if not blocks:
        return ""

    # Strategy 1: Explicit block of type 'abstract'
    for b in blocks:
        if b.get("type") == "abstract":
            zh = b.get("zh") or b.get("text") or ""
            if len(zh.strip()) >= 20:
                return zh.strip()

    # Strategy 2: Block immediately following a section header for 'abstract' / '摘要'
    for i, b in enumerate(blocks):
        txt = (b.get("text") or b.get("en") or "").strip().lower()
        zh = (b.get("zh") or "").strip()
        is_abstract_title = (
            b.get("type") in ("title", "aside_text", "text")
            and (txt in ("abstract", "abstract.", "abstract:") or "摘要" in zh)
            and len(txt) <= 25
        )
        if is_abstract_title:
            for nxt_idx in range(i + 1, min(i + 4, len(blocks))):
                nxt = blocks[nxt_idx]
                nxt_zh = nxt.get("zh") or ""
                if len(nxt_zh.strip()) >= 30 and nxt.get("type") in ("text", "para", "abstract"):
                    return nxt_zh.strip()

    # Strategy 3: Text block containing explicit keyword '摘要'
    for b in blocks[:20]:
        zh = b.get("zh") or ""
        if (zh.startswith("摘要") or "【摘要】" in zh) and len(zh) >= 35:
            return re.sub(r"^(?:【摘要】|摘要[：:]?)\s*", "", zh).strip()

    # Strategy 4: Largest text block on page 0 or page 1
    p1_blocks = [
        b for b in blocks
        if b.get("page") in (0, 1)
        and b.get("type") in ("text", "para")
        and b.get("zh")
        and not b.get("passthrough")
    ]
    if p1_blocks:
        longest = max(p1_blocks, key=lambda b: len(b.get("zh", "")))
        if len(longest.get("zh", "")) >= 60:
            return longest.get("zh", "").strip()

    return ""


def extract_tldr_from_abstract(text: str) -> dict:
    """
    Extract structured 4D overview from abstract text.
    Returns dict with keys: 'background', 'method', 'metrics', 'conclusion'.
    """
    if not text or len(text.strip()) < 20:
        return {}

    # Check if text already has explicit tag headers like 【研究背景与痛点】
    tag_bg = re.search(r'【?(?:研究背景与痛点|研究背景|核心痛点|痛点)】?[：:]?\s*([\s\S]+?)(?=【|$)', text)
    tag_meth = re.search(r'【?(?:核心创新与方案|核心创新|核心方法|方法与方案|方法|创新)】?[：:]?\s*([\s\S]+?)(?=【|$)', text)
    tag_metr = re.search(r'【?(?:实验性能与指标|关键指标|性能指标|指标|实验结论)】?[：:]?\s*([\s\S]+?)(?=【|$)', text)
    tag_conc = re.search(r'【?(?:工作价值与结论|现实意义|学术贡献|价值与结论|结论)】?[：:]?\s*([\s\S]+?)(?=【|$)', text)

    if any([tag_bg, tag_meth, tag_metr, tag_conc]):
        return {
            "background": tag_bg.group(1).strip() if tag_bg else "",
            "method": tag_meth.group(1).strip() if tag_meth else "",
            "metrics": tag_metr.group(1).strip() if tag_metr else "",
            "conclusion": tag_conc.group(1).strip() if tag_conc else "",
        }

    # Sentence segmentation
    sentences = [s.strip() for s in re.split(r'(?<=[。！？；\n])\s*', text.strip()) if len(s.strip()) > 5]
    if not sentences:
        return {}

    assigned = set()
    bg_s, meth_s, metr_s, conc_s = [], [], [], []

    # Pass 1: Method - explicit proposal / architecture design
    for i, s in enumerate(sentences):
        if i in assigned:
            continue
        if any(k in s for k in [
            '提出了一种', '我们提出', '本文提出', '我们介绍', '本文介绍',
            '我们构建', '提出了', '在这项工作中', '在本研究中', '一种新的简单网络架构',
            '完全基于注意力机制', '架构的核心是', '其核心是', '核心创新'
        ]):
            meth_s.append(s)
            assigned.add(i)

    # Pass 2: Background - traditional approaches / limitations / pain points
    for i, s in enumerate(sentences):
        if i in assigned:
            continue
        if any(k in s for k in [
            '主流', '传统', '现有', '复杂的', '受限', '瓶颈', '难以',
            '不足', '挑战', '尽管', '缺乏', '局限', '当前', '由于', '有限状态',
            '循环或卷积神经网络'
        ]):
            bg_s.append(s)
            assigned.add(i)

    # Pass 3: Metrics - quantitative evaluation / benchmark improvements
    for i, s in enumerate(sentences):
        if i in assigned:
            continue
        if any(k in s for k in [
            'BLEU', '提升', '提高', '超越', '准确率', '错误率', 'SOTA', '基准',
            '实验表明', '任务中', '评估', '测试集', '达到', '比现有', '绝对提升',
            '得分', '表现更优', '大幅减少了计算量', '首次超越'
        ]):
            metr_s.append(s)
            assigned.add(i)

    # Pass 4: Conclusion - impact, validation, generalization
    for i, s in enumerate(sentences):
        if i in assigned:
            continue
        if any(k in s for k in [
            '证明', '表明', '展现', '开创', '奠定', '新范式', '通用',
            '优势', '泛化', '推广到', '意味着', '结论', '高硬件效率'
        ]):
            conc_s.append(s)
            assigned.add(i)

    # Pass 5: Distribute remaining sentences to best fit empty slots
    for i, s in enumerate(sentences):
        if i in assigned:
            continue
        if not bg_s:
            bg_s.append(s)
        elif not meth_s:
            meth_s.append(s)
        elif not metr_s:
            metr_s.append(s)
        else:
            conc_s.append(s)
        assigned.add(i)

    # Fallback to ensure all 4 dimensions are populated if text contains multiple sentences
    all_s = sentences
    if not bg_s and all_s:
        bg_s.append(all_s[0])
    if not meth_s and all_s:
        meth_s.append(all_s[min(1, len(all_s) - 1)])
    if not metr_s and all_s:
        metr_s.append(all_s[min(2, len(all_s) - 1)])
    if not conc_s and all_s:
        conc_s.append(all_s[-1])

    return {
        "background": " ".join(bg_s).strip(),
        "method": " ".join(meth_s).strip(),
        "metrics": " ".join(metr_s).strip(),
        "conclusion": " ".join(conc_s).strip(),
    }


def extract_paper_tldr_from_blocks(blocks: list) -> dict:
    """Extract 4D TL;DR from a list of document blocks."""
    abstract_text = locate_abstract_text(blocks)
    if not abstract_text:
        return {}
    return extract_tldr_from_abstract(abstract_text)
