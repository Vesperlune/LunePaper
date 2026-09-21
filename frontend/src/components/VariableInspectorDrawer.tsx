import React, { useState, useMemo } from 'react';
import katex from 'katex';
import { MathText } from './MathText';
import type { GlobalVariableItem } from '../types';

interface VariableInspectorDrawerProps {
  isOpen: boolean;
  onClose: () => void;
  variables: GlobalVariableItem[];
  onJumpToEquation: (page: number, blockIdx: number) => void;
}

export const VariableInspectorDrawer: React.FC<VariableInspectorDrawerProps> = ({
  isOpen,
  onClose,
  variables,
  onJumpToEquation,
}) => {
  const [searchQuery, setSearchQuery] = useState('');
  const [expandedSym, setExpandedSym] = useState<string | null>(null);

  // Filter variables
  const filtered = useMemo(() => {
    if (!searchQuery.trim()) return variables;
    const q = searchQuery.toLowerCase().trim();
    return variables.filter(
      v =>
        v.cleanSymbol.toLowerCase().includes(q) ||
        v.name.toLowerCase().includes(q) ||
        v.desc.toLowerCase().includes(q)
    );
  }, [variables, searchQuery]);

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 overflow-hidden pointer-events-auto">
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-black/30 backdrop-blur-xs transition-opacity duration-300"
        onClick={onClose}
      />

      <div className="fixed inset-y-0 right-0 max-w-full flex pl-10">
        <div className="w-screen max-w-md liquid-glass-panel border-l border-white/60 shadow-2xl flex flex-col bg-white/90 backdrop-blur-xl animate-slide-left">
          {/* Drawer Header */}
          <div className="p-4 sm:p-5 border-b border-violet-100/80 flex items-center justify-between gap-3">
            <div className="flex items-center gap-2.5">
              <span className="flex items-center justify-center w-8 h-8 rounded-xl bg-violet-50/90 text-violet-700 border border-violet-200/80 shadow-2xs">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M4 19.5v-15A2.5 2.5 0 0 1 6.5 2H20v20H6.5a2.5 2.5 0 0 1-2.5-2.5Z" />
                  <path d="M6 10h10" />
                  <path d="M6 14h10" />
                </svg>
              </span>
              <div>
                <h3 className="text-base font-bold text-gray-900 tracking-tight flex items-center gap-2">
                  <span>公式变量全篇字典</span>
                  <span className="text-[11px] font-semibold text-violet-700 bg-violet-100/90 px-2 py-0.5 rounded-full border border-violet-200/60">
                    {variables.length} 符号
                  </span>
                </h3>
                <p className="text-[11px] text-gray-500 mt-0.5">
                  全篇数学符号语义聚合与公式溯源追踪
                </p>
              </div>
            </div>

            <button
              type="button"
              onClick={onClose}
              className="p-1.5 rounded-lg text-gray-400 hover:text-gray-700 hover:bg-violet-100/60 transition-colors cursor-pointer"
              title="关闭抽屉"
            >
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                <line x1="18" y1="6" x2="6" y2="18" />
                <line x1="6" y1="6" x2="18" y2="18" />
              </svg>
            </button>
          </div>

          {/* Search Bar */}
          <div className="p-3.5 border-b border-violet-100/60 bg-violet-50/30">
            <div className="relative">
              <input
                type="text"
                value={searchQuery}
                onChange={e => setSearchQuery(e.target.value)}
                placeholder="搜索符号 (如 Q, d_k, beta)..."
                className="w-full pl-8 pr-3 py-1.5 text-xs rounded-xl border border-violet-200/80 bg-white/80 focus:bg-white focus:outline-none focus:ring-2 focus:ring-violet-500/30 text-gray-800 placeholder-gray-400"
              />
              <svg
                width="13"
                height="13"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2.5"
                strokeLinecap="round"
                strokeLinejoin="round"
                className="absolute left-2.5 top-2 text-violet-500"
              >
                <circle cx="11" cy="11" r="8" />
                <line x1="21" y1="21" x2="16.65" y2="16.65" />
              </svg>
              {searchQuery && (
                <button
                  type="button"
                  onClick={() => setSearchQuery('')}
                  className="absolute right-2.5 top-2 text-gray-400 hover:text-gray-600 text-xs"
                >
                  清空
                </button>
              )}
            </div>
          </div>

          {/* Variable List */}
          <div className="flex-1 overflow-y-auto p-4 space-y-3 divide-y divide-violet-100/50">
            {filtered.length === 0 ? (
              <div className="py-12 text-center text-gray-400 text-xs">
                {variables.length === 0 ? '本文未检测到独立公式变量定义' : '未找到匹配的变量符号'}
              </div>
            ) : (
              filtered.map(item => {
                const isExpanded = expandedSym === item.cleanSymbol;
                const katexHtml = (() => {
                  try {
                    let raw = item.symbol.replace(/^\$|\$$/g, '').trim();
                    if (raw.includes('_') && !raw.includes('_{') && !raw.includes('\\mathrm') && !raw.includes('\\text')) {
                      raw = raw.replace(/([a-zA-Z]+)_([a-zA-Z0-9]+)/g, '$1_{\\mathrm{$2}}');
                    }
                    return katex.renderToString(raw, { throwOnError: false });
                  } catch {
                    return item.symbol;
                  }
                })();

                return (
                  <div key={item.cleanSymbol} className="pt-3 first:pt-0">
                    <div className="p-3 rounded-xl bg-white/60 hover:bg-violet-50/50 border border-violet-100/70 transition-all">
                      {/* Symbol Row */}
                      <div className="flex items-center justify-between gap-2">
                        <div className="flex items-center gap-2">
                          <span
                            className="inline-flex items-center justify-center min-w-[28px] px-2 py-0.5 rounded-lg bg-violet-100 text-violet-900 font-mono text-xs font-bold border border-violet-200/60 shadow-2xs"
                            dangerouslySetInnerHTML={{ __html: katexHtml }}
                          />
                          <span className="font-semibold text-xs text-gray-900 truncate">
                            <MathText text={item.name} />
                          </span>
                        </div>

                        <span className="text-[10px] font-medium text-violet-700 bg-violet-50 border border-violet-200/50 px-2 py-0.5 rounded-full shrink-0">
                          {item.count} 处引用
                        </span>
                      </div>

                      {/* Description */}
                      <p className="mt-1.5 text-[11.5px] text-gray-600 leading-relaxed">
                        <MathText text={item.desc} />
                      </p>

                      {/* Occurrences Toggle */}
                      {item.occurrences.length > 0 && (
                        <div className="mt-2.5 pt-2 border-t border-violet-100/60 flex items-center justify-between">
                          <button
                            type="button"
                            onClick={() => setExpandedSym(isExpanded ? null : item.cleanSymbol)}
                            className="inline-flex items-center gap-1 text-[11px] font-medium text-violet-700 hover:text-violet-900 cursor-pointer"
                          >
                            <span>出现于 {item.occurrences.length} 个公式块</span>
                            <svg
                              width="10"
                              height="10"
                              viewBox="0 0 24 24"
                              fill="none"
                              stroke="currentColor"
                              strokeWidth="2.5"
                              strokeLinecap="round"
                              strokeLinejoin="round"
                              className={`transform transition-transform ${isExpanded ? 'rotate-180' : ''}`}
                            >
                              <polyline points="6 9 12 15 18 9" />
                            </svg>
                          </button>

                          {/* Quick jump to first occurrence */}
                          <button
                            type="button"
                            onClick={() => {
                              const first = item.occurrences[0];
                              onJumpToEquation(first.page, first.blockIdx);
                              onClose();
                            }}
                            className="text-[10px] font-medium text-violet-600 hover:text-violet-800 hover:underline cursor-pointer"
                          >
                            跳转至首定义 (P.{item.occurrences[0].page})
                          </button>
                        </div>
                      )}

                      {/* Occurrences Expanded List */}
                      {isExpanded && (
                        <div className="mt-2 space-y-1.5 pl-2 border-l-2 border-violet-200">
                          {item.occurrences.map((occ, idx) => (
                            <button
                              key={`${occ.page}-${occ.blockIdx}-${idx}`}
                              type="button"
                              onClick={() => {
                                onJumpToEquation(occ.page, occ.blockIdx);
                                onClose();
                              }}
                              className="w-full text-left p-1.5 rounded-lg hover:bg-violet-100/70 text-[11px] text-gray-700 transition-colors flex items-center justify-between group cursor-pointer"
                            >
                              <span className="font-mono text-violet-800">
                                第 {occ.page} 页 · 公式 #{occ.blockIdx}
                              </span>
                              <span className="text-[10px] text-violet-500 opacity-0 group-hover:opacity-100 transition-opacity">
                                滚动定位
                              </span>
                            </button>
                          ))}
                        </div>
                      )}
                    </div>
                  </div>
                );
              })
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
