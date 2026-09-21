import React, { memo } from 'react';
import katex from 'katex';

interface MathTextProps {
  text?: string;
  className?: string;
}

/**
 * Renders mixed text containing LaTeX formulas ($...$, $$...$$, \(...\), or standalone commands).
 * Guaranteed to gracefully fallback to plain text if KaTeX encounters any syntax issues.
 */
export const MathText: React.FC<MathTextProps> = memo(({ text, className }) => {
  if (!text) return null;

  // Split by $$...$$, $...$, \(...\), or \[...\]
  const mathRegex = /(\$\$[\s\S]+?\$\$|\$[^\$\n]+?\$|\\\[[\s\S]+?\\\]|\\\([^\n]+?\\\))/g;
  const parts = text.split(mathRegex);

  return (
    <span className={className}>
      {parts.map((part, idx) => {
        if (!part) return null;

        let math = '';
        let isDisplay = false;

        if (part.startsWith('$$') && part.endsWith('$$') && part.length >= 4) {
          math = part.slice(2, -2).trim();
          isDisplay = true;
        } else if (part.startsWith('$') && part.endsWith('$') && part.length >= 2) {
          math = part.slice(1, -1).trim();
        } else if (part.startsWith('\\[') && part.endsWith('\\]') && part.length >= 4) {
          math = part.slice(2, -2).trim();
          isDisplay = true;
        } else if (part.startsWith('\\(') && part.endsWith('\\)') && part.length >= 4) {
          math = part.slice(2, -2).trim();
        }

        if (math) {
          try {
            const html = katex.renderToString(math, {
              displayMode: isDisplay,
              throwOnError: false,
            });
            return (
              <span
                key={idx}
                className={isDisplay ? 'block my-1 text-center overflow-x-auto' : 'inline-block mx-0.5 align-baseline text-[0.98em]'}
                dangerouslySetInnerHTML={{ __html: html }}
              />
            );
          } catch {
            return <span key={idx}>{part}</span>;
          }
        }

        // Check if plain part contains un-bracketed LaTeX commands like \sqrt{d_k} or \beta_1
        if (part.includes('\\') && /\\[a-zA-Z]+(?:\{[^}]*\}|_[a-zA-Z0-9{}]+|\^[a-zA-Z0-9{}]+)?/.test(part)) {
          const subTokens = part.split(/(\\[a-zA-Z]+(?:\{[^}]*\}|_[a-zA-Z0-9{}]+|\^[a-zA-Z0-9{}]+)?)/g);
          return (
            <React.Fragment key={idx}>
              {subTokens.map((sub, sIdx) => {
                if (sub.startsWith('\\') && /\\[a-zA-Z]/.test(sub)) {
                  try {
                    const html = katex.renderToString(sub, {
                      displayMode: false,
                      throwOnError: false,
                    });
                    return (
                      <span
                        key={sIdx}
                        className="inline-block mx-0.5 align-baseline text-[0.98em]"
                        dangerouslySetInnerHTML={{ __html: html }}
                      />
                    );
                  } catch {
                    return <span key={sIdx}>{sub}</span>;
                  }
                }
                return <span key={sIdx}>{sub}</span>;
              })}
            </React.Fragment>
          );
        }

        return <span key={idx}>{part}</span>;
      })}
    </span>
  );
});
