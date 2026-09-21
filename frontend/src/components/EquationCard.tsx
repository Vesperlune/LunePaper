import React, { useState, useMemo } from 'react';
import katex from 'katex';
import { extractFormulaVariables } from '../utils/variableExtractor';
import { MathText } from './MathText';
import type { VariableInfo } from '../types';

interface EquationCardProps {
  text: string;
  contextEn?: string;
  contextZh?: string;
  page?: number;
  idx?: number;
  onOpenVariableInspector?: () => void;
}

import { sanitizeLatexMath } from '../utils/latexSanitizer';

export function cleanLatexMath(latex: string): string {
  if (!latex) return '';
  const pre = latex
    .replace(/&amp;/g, '&')
    .replace(/\\_\{n\}\s*u\s*m\b/g, '_{\\mathrm{num}}')
    .replace(/step_\\mathrm\{num\}/g, 'step_{\\mathrm{num}}')
    .replace(/warmup_\\mathrm\{steps\}/g, 'warmup_{\\mathrm{steps}}')
    .replace(/-0\.\s+5/g, '-0.5')
    .replace(/-1\.\s+5/g, '-1.5')
    .replace(/\\\s+where\b/g, '\\\\ \\text{where }')
    .replace(/\.\s*\.\s*\./g, '\\dots');
  return sanitizeLatexMath(pre);
}

export const EquationCard: React.FC<EquationCardProps> = ({
  text,
  contextEn = '',
  contextZh = '',
  page,
  idx,
  onOpenVariableInspector,
}) => {
  const [copied, setCopied] = useState(false);
  const [isZoomOpen, setIsZoomOpen] = useState(false);
  const [isVarsExpanded, setIsVarsExpanded] = useState(false);

  // Clean and extract core LaTeX code
  const rawLatex = useMemo(() => {
    let clean = (text || '').trim();
    if (clean.startsWith('$$') && clean.endsWith('$$')) {
      clean = clean.slice(2, -2).trim();
    } else if (clean.startsWith('\\[') && clean.endsWith('\\]')) {
      clean = clean.slice(2, -2).trim();
    }
    return cleanLatexMath(clean);
  }, [text]);

  // Extract variables from formula and context
  const variables: VariableInfo[] = useMemo(() => {
    return extractFormulaVariables(rawLatex, contextEn, contextZh);
  }, [rawLatex, contextEn, contextZh]);

  // Render HTML via KaTeX
  const html = useMemo(() => {
    try {
      return katex.renderToString(rawLatex, {
        displayMode: true,
        throwOnError: false,
      });
    } catch {
      return '';
    }
  }, [rawLatex]);

  const handleCopy = async (e: React.MouseEvent) => {
    e.stopPropagation();
    try {
      await navigator.clipboard.writeText(rawLatex);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch (err) {
      console.error('Failed to copy LaTeX: ', err);
    }
  };

  return (
    <div
      id={page !== undefined && idx !== undefined ? `eq-item-p${page}-i${idx}` : undefined}
      className="relative group liquid-glass-card mx-2 my-2.5 px-5 py-4 rounded-2xl shadow-xs hover:shadow-md transition-all"
    >
      {/* Top Action Bar */}
      <div className="flex items-center justify-between gap-2 mb-1.5 opacity-90 transition-opacity">
        <div className="flex items-center gap-2">
          <span className="text-[10px] font-bold uppercase tracking-wider text-violet-800 bg-violet-100/90 px-2 py-0.5 rounded-md border border-violet-200/60 shadow-2xs">
            Formula
          </span>
          {variables.length > 0 && (
            <button
              type="button"
              onClick={() => setIsVarsExpanded(prev => !prev)}
              className="inline-flex items-center gap-1.5 text-[11px] font-medium text-violet-700 hover:text-violet-900 liquid-glass-pill hover:bg-violet-100/90 px-2.5 py-0.5 rounded-md transition-all cursor-pointer"
              title="查看公式中各个变量的定义与物理意义"
            >
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="shrink-0 text-violet-500">
                <path d="M4 19.5v-15A2.5 2.5 0 0 1 6.5 2H20v20H6.5a2.5 2.5 0 0 1-2.5-2.5Z" />
                <path d="M6 10h10" />
                <path d="M6 14h10" />
              </svg>
              <span>变量词典 ({variables.length})</span>
              <svg
                width="10"
                height="10"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2.5"
                strokeLinecap="round"
                strokeLinejoin="round"
                className={`transition-transform duration-200 ${isVarsExpanded ? 'rotate-180' : ''}`}
              >
                <polyline points="6 9 12 15 18 9" />
              </svg>
            </button>
          )}
        </div>

        {/* Action Buttons */}
        <div className="flex items-center gap-1.5">
          <button
            type="button"
            onClick={handleCopy}
            className={`inline-flex items-center gap-1 text-[11px] font-medium px-2.5 py-1 rounded-lg transition-all cursor-pointer ${
              copied
                ? 'bg-emerald-100 text-emerald-700 border border-emerald-300 shadow-2xs'
                : 'liquid-glass-pill hover:bg-violet-50/90 text-gray-700 hover:text-violet-800'
            }`}
            title="复制标准 LaTeX 源码"
          >
            {copied ? (
              <>
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                  <polyline points="20 6 9 17 4 12" />
                </svg>
                <span>已复制</span>
              </>
            ) : (
              <>
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <rect x="9" y="9" width="13" height="13" rx="2" ry="2" />
                  <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
                </svg>
                <span>复制 LaTeX</span>
              </>
            )}
          </button>

          <button
            type="button"
            onClick={() => setIsZoomOpen(true)}
            className="inline-flex items-center gap-1 text-[11px] font-medium px-2 py-1 rounded-lg liquid-glass-pill hover:bg-violet-50/90 text-gray-700 hover:text-violet-800 transition-all cursor-pointer"
            title="全屏高清放大观察"
          >
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <circle cx="11" cy="11" r="8" />
              <line x1="21" y1="21" x2="16.65" y2="16.65" />
              <line x1="11" y1="8" x2="11" y2="14" />
              <line x1="8" y1="11" x2="14" y2="11" />
            </svg>
            <span>放大</span>
          </button>
        </div>
      </div>

      {/* Main KaTeX Render View */}
      <div
        className="text-center py-3 overflow-x-auto select-text scrollbar-thin"
        dangerouslySetInnerHTML={{ __html: html || rawLatex }}
      />

      {/* Expandable Variable Dictionary Drawer */}
      {isVarsExpanded && variables.length > 0 && (
        <div className="mt-3 pt-3 border-t border-violet-100/80 animate-fade-in text-left">
          <div className="flex items-center gap-1.5 text-xs font-semibold text-gray-700 mb-2">
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="text-violet-600 shrink-0">
              <path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z" />
              <path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z" />
            </svg>
            <span>公式变量与符号解析</span>
            {onOpenVariableInspector ? (
              <button
                type="button"
                onClick={onOpenVariableInspector}
                className="text-[10px] text-violet-700 hover:text-violet-900 font-medium ml-auto hover:underline cursor-pointer"
              >
                打开全篇符号字典 &rarr;
              </button>
            ) : (
              <span className="text-[10px] text-gray-400 font-normal ml-auto">提取自论文前后文与标准定义</span>
            )}
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            {variables.map((v, idx) => (
              <div
                key={idx}
                className="flex items-start gap-2.5 p-2.5 rounded-xl liquid-glass-pill hover:bg-violet-50/90 transition-all"
              >
                <div
                  className="shrink-0 font-bold text-violet-900 bg-white/90 px-1.5 py-0.5 rounded border border-violet-200/70 text-xs shadow-2xs"
                  dangerouslySetInnerHTML={{
                    __html: katex.renderToString(v.symbol.replace(/\$/g, ''), { throwOnError: false }),
                  }}
                />
                <div className="min-w-0 flex-1">
                  <div className="text-xs font-semibold text-gray-800 truncate">
                    <MathText text={v.name} />
                  </div>
                  <div className="text-[11px] text-gray-600 line-clamp-2 leading-tight mt-0.5">
                    <MathText text={v.desc} />
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Fullscreen Zoom Modal */}
      {isZoomOpen && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40 backdrop-blur-md animate-fade-in"
          onClick={() => setIsZoomOpen(false)}
        >
          <div
            className="relative w-full max-w-4xl max-h-[85vh] liquid-glass-card bg-white/95 rounded-3xl p-8 shadow-2xl border border-white/80 overflow-y-auto"
            onClick={e => e.stopPropagation()}
          >
            {/* Modal Header */}
            <div className="flex items-center justify-between pb-4 mb-6 border-b border-gray-100">
              <div className="flex items-center gap-3">
                <div className="p-2 rounded-xl bg-violet-100 text-violet-700">
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M4 20h4l7-16h5" />
                    <path d="M9 12h6" />
                  </svg>
                </div>
                <div>
                  <h3 className="text-base font-bold text-gray-900">公式高清放大观察</h3>
                  <p className="text-xs text-gray-400">支持横向滚动与 LaTeX 源码快速复制</p>
                </div>
              </div>

              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={handleCopy}
                  className="inline-flex items-center gap-1.5 text-xs font-medium px-3 py-1.5 rounded-xl bg-violet-50 hover:bg-violet-100 text-violet-700 border border-violet-200/80 transition-all cursor-pointer"
                >
                  {copied ? '已复制 LaTeX' : '复制 LaTeX 代码'}
                </button>
                <button
                  type="button"
                  onClick={() => setIsZoomOpen(false)}
                  className="p-1.5 rounded-xl text-gray-400 hover:text-gray-700 hover:bg-gray-100 transition-all cursor-pointer"
                  title="关闭 (Esc)"
                >
                  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <line x1="18" y1="6" x2="6" y2="18" />
                    <line x1="6" y1="6" x2="18" y2="18" />
                  </svg>
                </button>
              </div>
            </div>

            {/* Modal Formula Body (Enlarged) */}
            <div className="py-8 px-4 my-2 text-center overflow-x-auto bg-gray-50/60 rounded-2xl border border-gray-100">
              <div
                className="text-xl inline-block"
                dangerouslySetInnerHTML={{
                  __html: katex.renderToString(rawLatex, { displayMode: true, throwOnError: false }),
                }}
              />
            </div>

            {/* LaTeX Raw Source Code Box */}
            <div className="mt-6">
              <div className="text-xs font-semibold text-gray-500 mb-1.5">LaTeX 源码</div>
              <pre className="p-3 rounded-xl bg-gray-900 text-gray-100 text-xs font-mono overflow-x-auto selection:bg-violet-600">
                {rawLatex}
              </pre>
            </div>

            {/* Variables Breakdown in Modal */}
            {variables.length > 0 && (
              <div className="mt-6">
                <div className="text-xs font-semibold text-gray-500 mb-2">变量与符号对照</div>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                  {variables.map((v, idx) => (
                    <div key={idx} className="flex items-start gap-2.5 p-2.5 rounded-xl bg-violet-50/60 border border-violet-100">
                      <div
                        className="font-bold text-violet-900 bg-white px-2 py-0.5 rounded border border-violet-200 text-xs"
                        dangerouslySetInnerHTML={{
                          __html: katex.renderToString(v.symbol.replace(/\$/g, ''), { throwOnError: false }),
                        }}
                      />
                      <div>
                        <div className="text-xs font-semibold text-gray-900">
                          <MathText text={v.name} />
                        </div>
                        <div className="text-xs text-gray-600 mt-0.5">
                          <MathText text={v.desc} />
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
};
