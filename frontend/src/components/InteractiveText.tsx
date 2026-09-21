import React, { useMemo } from 'react';
import ReactMarkdown, { defaultUrlTransform } from 'react-markdown';
import remarkMath from 'remark-math';
import rehypeKatex from 'rehype-katex';
import type { ReferenceItem } from '../types';
import { CitationPopover } from './CitationPopover';
import { parseCitationNumbers } from '../utils/referenceParser';
import { sanitizeLatexMath } from '../utils/latexSanitizer';

interface InteractiveTextProps {
  text: string;
  refIndex: Record<string, ReferenceItem>;
  onJumpToReference?: (id: string, page?: number) => void;
  className?: string;
  isRefBlock?: boolean;
}

/**
 * Transforms plain citation notation like [12], [29, 2, 5], [1-3] into markdown citation links
 * like [12](cite:12), protecting mathematical formula blocks and verifying against refIndex.
 */
function injectCitationLinks(
  text: string,
  refIndex: Record<string, ReferenceItem>,
  isRefBlock: boolean = false
): string {
  if (!text) return '';

  const totalKnownRefs = refIndex ? Object.keys(refIndex).length : 0;

  // Split out LaTeX math delimiters to prevent mutating formulas
  // ($$...$$, $...$, \[...\], \(...\))
  const mathRegex = /(\$\$[\s\S]+?\$\$|\$[^\$\n]+?\$|\\\[[\s\S]+?\\\]|\\\([^\n]+?\\\))/g;
  const parts = text.split(mathRegex);

  return parts.map((part, partIdx) => {
    // Check if this part is a math formula
    if (part.startsWith('$') || part.startsWith('\\(') || part.startsWith('\\[') || part.endsWith('$')) {
      // Check for OCR artifact where citation was wrapped inside $ [50] $ or $ [12, 13] $
      const ocrMathCitation = part.match(/^\$\s*(\[\s*\d+(?:[\s,\-–—]+\d+)*\s*\])\s*\$$/);
      if (ocrMathCitation) {
        const nums = parseCitationNumbers(ocrMathCitation[1]);
        const validNums = totalKnownRefs > 0
          ? nums.filter(num => refIndex[num] !== undefined)
          : nums.filter(num => parseInt(num, 10) >= 1 && parseInt(num, 10) <= 200);

        if (validNums.length > 0) {
          return validNums.map(num => `[${num}](cite:${num})`).join(', ');
        }
      }
      return sanitizeLatexMath(part);
    }

    // In a reference item definition block itself, do not convert the leading item index (e.g. "[1] ")
    let currentPart = part;
    let leadingPrefix = '';
    if (isRefBlock && partIdx === 0) {
      const leadingMatch = currentPart.match(/^\s*(?:\[\s*\d+\s*\]|\d+\.\s+)/);
      if (leadingMatch) {
        leadingPrefix = leadingMatch[0];
        currentPart = currentPart.slice(leadingPrefix.length);
      }
    }

    // Match citation brackets not part of existing links or images
    const transformed = currentPart.replace(/(?<!!)(?:\[\s*(\d+(?:[\s,\-–—]+\d+)*)\s*\])(?!\()/g, (match) => {
      const nums = parseCitationNumbers(match);
      if (nums.length === 0) return match;

      // CRITICAL ACCURACY CHECK:
      // If we have parsed references in the paper, ONLY convert numbers that actually exist in the bibliography!
      // This eliminates false positives for mathematical intervals like [0, 1], shapes like [512], etc.
      const validNums = totalKnownRefs > 0
        ? nums.filter(num => refIndex[num] !== undefined)
        : nums.filter(num => {
            const n = parseInt(num, 10);
            return n >= 1 && n <= 100;
          });

      if (validNums.length === 0) {
        return match; // Leave original plain text untouched!
      }

      // Render verified citation links
      return validNums.map(num => `[${num}](cite:${num})`).join(', ');
    });

    return leadingPrefix + transformed;
  }).join('');
}

export const InteractiveText = React.memo<InteractiveTextProps>(({
  text,
  refIndex,
  onJumpToReference,
  className = '',
  isRefBlock = false,
}) => {
  const processedText = useMemo(
    () => injectCitationLinks(text, refIndex, isRefBlock),
    [text, refIndex, isRefBlock]
  );

  return (
    <div className={`interactive-text leading-relaxed ${className}`}>
      <ReactMarkdown
        remarkPlugins={[remarkMath]}
        rehypePlugins={[[rehypeKatex, { throwOnError: false }]]}
        urlTransform={(url) => (url.startsWith('cite:') ? url : defaultUrlTransform(url))}
        components={{
          p: ({ children }) => <span>{children}</span>,
          a: ({ href, children }) => {
            if (href?.startsWith('cite:')) {
              const citeId = href.slice(5);
              const refItem = refIndex[citeId];
              return (
                <CitationPopover
                  id={citeId}
                  refItem={refItem}
                  onJumpToReference={onJumpToReference}
                >
                  <span
                    className="inline-flex items-center align-baseline font-mono text-[0.82em] font-semibold text-violet-700 bg-violet-50/90 hover:bg-violet-600 hover:text-white border border-violet-200/80 px-1 py-0.2 mx-0.5 rounded-md transition-all duration-150 shadow-2xs hover:shadow-xs active:scale-95 cursor-pointer select-none"
                    title={`查看参考文献 [${citeId}]`}
                  >
                    [{children}]
                  </span>
                </CitationPopover>
              );
            }
            return (
              <a
                href={href}
                target="_blank"
                rel="noopener noreferrer"
                className="text-violet-600 hover:text-violet-800 underline decoration-violet-300 hover:decoration-violet-600 transition-colors"
              >
                {children}
              </a>
            );
          },
        }}
      >
        {processedText}
      </ReactMarkdown>
    </div>
  );
});

InteractiveText.displayName = 'InteractiveText';

