import React, { useState } from 'react';
import { MathText } from './MathText';
import type { PaperTLDR } from '../types';

interface PaperTLDRCardProps {
  tldr?: PaperTLDR;
  loading?: boolean;
}

export const PaperTLDRCard: React.FC<PaperTLDRCardProps> = ({ tldr, loading = false }) => {
  const [isExpanded, setIsExpanded] = useState(true);

  if (!tldr && !loading) return null;

  const hasContent = Boolean(
    tldr && (tldr.background || tldr.method || tldr.metrics || tldr.conclusion)
  );

  if (!hasContent && !loading) return null;

  return (
    <div className="relative mx-auto my-4 max-w-4xl px-3 sm:px-6">
      <div className="liquid-glass-card rounded-2xl p-4 sm:p-5 border border-white/60 shadow-sm transition-all duration-300">
        {/* Header */}
        <div className="flex items-center justify-between gap-3 pb-3 border-b border-violet-100/70">
          <div className="flex items-center gap-2.5">
            <span className="flex items-center justify-center w-8 h-8 rounded-xl bg-violet-50/90 text-violet-700 border border-violet-200/80 shadow-2xs">
              <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="m9 11 3 3L22 4" />
                <path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11" />
              </svg>
            </span>
            <div>
              <div className="flex items-center gap-2">
                <h3 className="text-sm sm:text-base font-bold text-gray-900 tracking-tight">
                  论文结构化速读
                </h3>
                <span className="text-[10px] font-semibold text-violet-700 bg-violet-100/90 px-2 py-0.5 rounded-full border border-violet-200/50">
                  Paper TL;DR
                </span>
              </div>
              <p className="text-[11px] text-gray-500 mt-0.5">
                大模型基于论文摘要提炼的四维核心要点
              </p>
            </div>
          </div>

          <button
            type="button"
            onClick={() => setIsExpanded(prev => !prev)}
            className="inline-flex items-center gap-1.5 px-3 py-1 rounded-lg text-xs font-medium text-violet-800 liquid-glass-pill hover:bg-violet-100/80 transition-all cursor-pointer"
            title={isExpanded ? '收起导读要点' : '展开完整导读'}
          >
            <span>{isExpanded ? '收起' : '展开'}</span>
            <svg
              width="12"
              height="12"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2.5"
              strokeLinecap="round"
              strokeLinejoin="round"
              className={`transform transition-transform duration-200 ${isExpanded ? 'rotate-180' : ''}`}
            >
              <polyline points="6 9 12 15 18 9" />
            </svg>
          </button>
        </div>

        {/* Content Body */}
        {loading && !hasContent ? (
          <div className="py-6 flex flex-col items-center justify-center text-center">
            <div className="w-6 h-6 border-2 border-violet-600 border-t-transparent rounded-full animate-spin mb-2" />
            <span className="text-xs text-violet-700 font-medium">正在提炼论文核心导读...</span>
          </div>
        ) : (
          isExpanded && (
            <div className="mt-3.5 grid grid-cols-1 md:grid-cols-2 gap-3 text-xs">
              {/* 1. 研究背景与痛点 */}
              {tldr?.background && (
                <div className="p-3.5 rounded-xl bg-violet-50/50 border border-violet-100/80 flex flex-col gap-1.5">
                  <div className="flex items-center gap-1.5 font-semibold text-violet-950">
                    <span className="w-1.5 h-1.5 rounded-full bg-violet-600 shrink-0" />
                    <span>研究背景与核心痛点</span>
                  </div>
                  <p className="text-gray-700 leading-relaxed text-[11.5px]">
                    <MathText text={tldr.background} />
                  </p>
                </div>
              )}

              {/* 2. 核心创新与方案 */}
              {tldr?.method && (
                <div className="p-3.5 rounded-xl bg-blue-50/50 border border-blue-100/80 flex flex-col gap-1.5">
                  <div className="flex items-center gap-1.5 font-semibold text-blue-950">
                    <span className="w-1.5 h-1.5 rounded-full bg-blue-600 shrink-0" />
                    <span>核心创新与方法架构</span>
                  </div>
                  <p className="text-gray-700 leading-relaxed text-[11.5px]">
                    <MathText text={tldr.method} />
                  </p>
                </div>
              )}

              {/* 3. 实验性能与指标 */}
              {tldr?.metrics && (
                <div className="p-3.5 rounded-xl bg-emerald-50/50 border border-emerald-100/80 flex flex-col gap-1.5">
                  <div className="flex items-center gap-1.5 font-semibold text-emerald-950">
                    <span className="w-1.5 h-1.5 rounded-full bg-emerald-600 shrink-0" />
                    <span>实验基准与关键指标</span>
                  </div>
                  <p className="text-gray-700 leading-relaxed text-[11.5px]">
                    <MathText text={tldr.metrics} />
                  </p>
                </div>
              )}

              {/* 4. 工作价值与结论 */}
              {tldr?.conclusion && (
                <div className="p-3.5 rounded-xl bg-amber-50/50 border border-amber-100/80 flex flex-col gap-1.5">
                  <div className="flex items-center gap-1.5 font-semibold text-amber-950">
                    <span className="w-1.5 h-1.5 rounded-full bg-amber-600 shrink-0" />
                    <span>学术价值与现实意义</span>
                  </div>
                  <p className="text-gray-700 leading-relaxed text-[11.5px]">
                    <MathText text={tldr.conclusion} />
                  </p>
                </div>
              )}
            </div>
          )
        )}
      </div>
    </div>
  );
};
