import type { BlockData, ReferenceItem } from '../types';

/**
 * Parses individual reference text lines/blocks into structured ReferenceItems.
 */
export function parseReferenceText(rawText: string, page: number, idx: number): ReferenceItem[] {
  const items: ReferenceItem[] = [];
  if (!rawText) return items;

  // Split multi-reference paragraphs if any (e.g. "[1] ... \n[2] ...")
  const lines = rawText.split(/(?=\[\d+\]|\n\d+\.\s+)/).map(s => s.trim()).filter(Boolean);

  for (const line of lines) {
    const mNum = line.match(/^(?:\[(\d+)\]|(\d+)\.\s+)\s*([\s\S]+)$/);
    if (!mNum) {
      // If it's a continuation or single unnumbered ref
      continue;
    }

    const id = mNum[1] || mNum[2];
    const content = mNum[3].trim();

    // Extract Year (e.g. 2017, (2016))
    const yearMatches = [...content.matchAll(/\b(19\d{2}|20\d{2})\b/g)];
    const year = yearMatches.length > 0 ? yearMatches[yearMatches.length - 1][1] : undefined;

    // Extract arXiv ID if present
    const arxivMatch = content.match(/(?:arxiv:?\s*|abs\/|arXiv:\s*)(\d{4}\.\d{4,5}(?:v\d+)?)/i);
    const arxivId = arxivMatch ? arxivMatch[1] : undefined;

    // Extract Authors, Title, and Venue
    // Standard academic format: Authors. Title. Venue/Journal, Year.
    // Or: Authors, "Title," Venue, Year.
    let authors = '';
    let title = '';
    let venueYear = '';

    // Check if title is enclosed in quotes
    const quoteMatch = content.match(/^(.*?)[,.]?\s*["“](.+?)["”][,.]?\s*([\s\S]*)$/);
    if (quoteMatch) {
      authors = quoteMatch[1].trim();
      title = quoteMatch[2].trim();
      venueYear = quoteMatch[3].trim();
    } else {
      // Split by full stop
      const parts = content.split(/(?<=\w\w)\.\s+(?=[A-Z0-9])/).map(p => p.trim()).filter(Boolean);
      if (parts.length >= 3) {
        authors = parts[0];
        title = parts[1];
        venueYear = parts.slice(2).join('. ');
      } else if (parts.length === 2) {
        authors = parts[0];
        title = parts[1];
      } else {
        title = content;
      }
    }

    // Clean up authors (limit length if too long)
    if (authors.length > 100) {
      const firstEtAl = authors.split(/[,&]/)[0].trim();
      authors = `${firstEtAl} et al.`;
    }

    items.push({
      id,
      page,
      idx,
      raw: line,
      authors: authors || undefined,
      title: title || content,
      venueYear: venueYear || undefined,
      year,
      arxivId,
    });
  }

  return items;
}

/**
 * Builds a fast lookup table: id -> ReferenceItem from all paper blocks.
 */
export function buildReferenceIndex(blocks: BlockData[]): Record<string, ReferenceItem> {
  const index: Record<string, ReferenceItem> = {};
  if (!blocks || blocks.length === 0) return index;

  let inReferences = false;

  for (const b of blocks) {
    const textLower = ((b.en || '') + ' ' + (b.zh || '')).toLowerCase().trim();

    // Check section heading
    if (b.type === 'title' || b.type === 'header') {
      if (/references|bibliography|参考文献/i.test(textLower)) {
        inReferences = true;
      } else if (inReferences && /^[1-9]\s+|appendix|附录/i.test(textLower)) {
        // Leaving references into appendix
        inReferences = false;
      }
    }

    if (b.type === 'ref_text' || inReferences || /^\[\d+\]\s+/.test(b.en || '') || /^\[\d+\]\s+/.test(b.zh || '')) {
      const parsed = parseReferenceText(b.en || b.zh || '', b.page, b.idx);
      for (const item of parsed) {
        if (!index[item.id]) {
          index[item.id] = item;
        }
      }
    }
  }

  return index;
}

/**
 * Checks if a string contains bracketed citation references like [1], [1, 2], [1-3], [12].
 */
export const CITATION_REGEX = /\[\s*(\d+(?:[\s,\-–—]+\d+)*)\s*\]/g;

export interface CitationMatch {
  raw: string;          // e.g. "[29, 2, 5]"
  nums: string[];       // e.g. ["29", "2", "5"]
  isRange: boolean;     // e.g. [1-3]
}

/**
 * Parses citation numbers out of bracket notation.
 * e.g. "[29, 2, 5]" -> ["29", "2", "5"]
 * e.g. "[1-3]" -> ["1", "2", "3"]
 * Note: Academic citations are strictly 1-based (>= 1). 0 is excluded.
 */
export function parseCitationNumbers(citationBracket: string): string[] {
  const inner = citationBracket.replace(/[\[\]]/g, '').trim();
  const tokens = inner.split(/[,;\s]+/).map(t => t.trim()).filter(Boolean);
  const result: string[] = [];

  for (const tok of tokens) {
    const rangeMatch = tok.match(/^(\d+)[-–—](\d+)$/);
    if (rangeMatch) {
      const start = parseInt(rangeMatch[1], 10);
      const end = parseInt(rangeMatch[2], 10);
      // Valid citation range: start >= 1, start < end, span at most 15
      if (start >= 1 && start < end && end - start <= 15) {
        for (let i = start; i <= end; i++) {
          result.push(String(i));
        }
        continue;
      }
    }
    const singleMatch = tok.match(/^(\d+)$/);
    if (singleMatch) {
      const val = parseInt(singleMatch[1], 10);
      // Citation IDs in papers are >= 1 and usually < 1000
      if (val >= 1 && val < 1000) {
        result.push(String(val));
      }
    }
  }

  return result;
}
