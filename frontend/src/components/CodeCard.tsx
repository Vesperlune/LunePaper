import React, { useState, useMemo } from 'react';
import { cleanCodeText, detectCodeLanguage } from '../utils/codeDetector';

interface CodeCardProps {
  code: string;
  caption?: string;
  captionZh?: string;
  page?: number;
  idx?: number;
}

/**
 * Tokenizes simple code lines for lightweight syntax styling matching LunePaper's light purple theme.
 */
function renderSyntaxHighlightedLine(line: string) {
  if (!line) return <span>&nbsp;</span>;

  // Comment
  if (line.trim().startsWith('#') || line.trim().startsWith('//')) {
    return <span className="text-slate-400 italic font-mono">{line}</span>;
  }

  // Simple token regex: strings, keywords, numbers, function calls
  const tokenRegex = /(["'][^"']*["']|\b(?:def|class|return|for|in|while|if|elif|else|import|from|as|lambda|try|except|with|yield|pass|break|continue)\b|\b(?:torch|nn|np|self)\b|\b\d+(?:\.\d+)?\b|[a-zA-Z_]\w*(?=\s*\()|[=+\-*\/%@<>&|^~:]+|[^\s\w=+\-*\/%@<>&|^~:"]+)/g;

  const parts = line.split(tokenRegex);

  return (
    <span>
      {parts.map((token, i) => {
        if (!token) return null;

        // String literal -> Emerald green
        if ((token.startsWith('"') && token.endsWith('"')) || (token.startsWith("'") && token.endsWith("'"))) {
          return <span key={i} className="text-emerald-700 font-medium">{token}</span>;
        }
        // Python / code keywords -> Bold vibrant violet
        if (/^(?:def|class|return|for|in|while|if|elif|else|import|from|as|lambda|try|except|with|yield|pass|break|continue)$/.test(token)) {
          return <span key={i} className="text-violet-700 font-bold">{token}</span>;
        }
        // Core libraries -> Indigo
        if (/^(?:torch|nn|np|self)$/.test(token)) {
          return <span key={i} className="text-indigo-600 font-semibold">{token}</span>;
        }
        // Numbers -> Warm amber
        if (/^\d+(?:\.\d+)?$/.test(token)) {
          return <span key={i} className="text-amber-700 font-medium">{token}</span>;
        }
        // Function calls -> Blue
        if (/^[a-zA-Z_]\w*$/.test(token) && line.indexOf(`${token}(`) !== -1) {
          return <span key={i} className="text-blue-700 font-medium">{token}</span>;
        }
        // Operators -> Violet accent
        if (/^[=+\-*\/%@<>&|^~:]+$/.test(token)) {
          return <span key={i} className="text-violet-600 font-bold">{token}</span>;
        }

        // Standard identifiers -> Dark slate
        return <span key={i} className="text-slate-800">{token}</span>;
      })}
    </span>
  );
}

export const CodeCard: React.FC<CodeCardProps> = ({
  code,
  caption,
  captionZh,
  page,
  idx,
}) => {
  const [copied, setCopied] = useState(false);

  const cleanCode = useMemo(() => cleanCodeText(code), [code]);
  const lines = useMemo(() => cleanCode.split('\n'), [cleanCode]);
  const lang = useMemo(() => detectCodeLanguage(cleanCode), [cleanCode]);

  // Extract function title if exists (e.g. def chunk_dplr)
  const fnMatch = cleanCode.match(/(?:def|class|Algorithm)\s+([a-zA-Z0-9_]+)/);
  const titleDisplay = fnMatch ? fnMatch[0] : caption || `${lang} 代码实现`;

  const handleCopy = () => {
    navigator.clipboard.writeText(cleanCode).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  };

  return (
    <div
      id={page && idx !== undefined ? `code-item-p${page}-i${idx}` : undefined}
      className="my-3 mx-2 rounded-2xl overflow-hidden border border-violet-200/90 bg-white/95 backdrop-blur-md shadow-[0_4px_20px_-4px_rgba(139,127,199,0.14)] text-slate-800 font-mono text-xs transition-all hover:border-violet-300 hover:shadow-[0_8px_28px_-4px_rgba(139,127,199,0.22)]"
    >
      {/* Code Card Toolbar Header */}
      <div className="flex items-center justify-between px-4 py-2.5 bg-gradient-to-r from-violet-50/95 via-purple-50/60 to-white/95 border-b border-violet-200/70 select-none">
        <div className="flex items-center gap-2.5 min-w-0">
          {/* Terminal dots */}
          <div className="flex items-center gap-1.5 shrink-0">
            <span className="w-2.5 h-2.5 rounded-full bg-rose-400/90 inline-block shadow-2xs" />
            <span className="w-2.5 h-2.5 rounded-full bg-amber-400/90 inline-block shadow-2xs" />
            <span className="w-2.5 h-2.5 rounded-full bg-emerald-400/90 inline-block shadow-2xs" />
          </div>

          <span className="px-2 py-0.5 rounded-md bg-violet-100 text-violet-700 font-bold text-[10px] tracking-wider uppercase border border-violet-200/90 shadow-2xs shrink-0">
            {lang}
          </span>

          <span className="text-violet-950 font-bold text-xs truncate max-w-sm font-mono">
            {titleDisplay}
          </span>
        </div>

        <div className="flex items-center gap-3 shrink-0">
          <span className="text-[11px] text-violet-400 font-medium hidden sm:inline">
            {lines.length} 行
          </span>

          <button
            type="button"
            onClick={handleCopy}
            className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg text-[11px] font-medium text-violet-700 hover:text-violet-900 bg-white hover:bg-violet-50 border border-violet-200/90 shadow-2xs hover:shadow-xs transition-all cursor-pointer active:scale-95"
            title="复制代码到剪贴板"
          >
            {copied ? (
              <>
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" className="text-emerald-600">
                  <polyline points="20 6 9 17 4 12" />
                </svg>
                <span className="text-emerald-600 font-semibold">已复制</span>
              </>
            ) : (
              <>
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="text-violet-500">
                  <rect width="14" height="14" x="8" y="8" rx="2" ry="2" />
                  <path d="M4 16c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2h10c1.1 0 2 .9 2 2" />
                </svg>
                <span>复制代码</span>
              </>
            )}
          </button>
        </div>
      </div>

      {/* Code Editor Body with Line Numbers */}
      <div className="relative overflow-x-auto p-3.5 text-xs leading-relaxed selection:bg-violet-100 selection:text-violet-900 bg-white">
        <table className="w-full border-collapse">
          <tbody>
            {lines.map((line, lineIdx) => (
              <tr key={lineIdx} className="hover:bg-violet-50/40 transition-colors">
                <td className="w-10 pr-3.5 text-right text-violet-300 select-none font-mono text-[11px] align-top border-r border-violet-100/80">
                  {lineIdx + 1}
                </td>
                <td className="pl-3.5 whitespace-pre font-mono text-slate-800">
                  {renderSyntaxHighlightedLine(line)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Optional Caption Footer */}
      {(caption || captionZh) && (
        <div className="px-4 py-2.5 bg-violet-50/60 border-t border-violet-200/70 text-[11px] text-slate-600 flex flex-col gap-1">
          {caption && <div className="font-sans italic text-slate-700 font-medium">{caption}</div>}
          {captionZh && captionZh !== caption && (
            <div className="font-sans text-violet-950 font-medium">{captionZh}</div>
          )}
        </div>
      )}
    </div>
  );
};

