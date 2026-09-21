import React, { useState, useRef, useEffect } from 'react';
import { createPortal } from 'react-dom';
import type { ReferenceItem } from '../types';

interface CitationPopoverProps {
  id: string;
  refItem?: ReferenceItem;
  children: React.ReactNode;
  onJumpToReference?: (id: string, page?: number) => void;
}

export const CitationPopover: React.FC<CitationPopoverProps> = ({
  id,
  refItem,
  children,
  onJumpToReference,
}) => {
  const [isOpen, setIsOpen] = useState(false);
  const [coords, setCoords] = useState<{ top: number; left: number; placeAbove: boolean }>({
    top: 0,
    left: 0,
    placeAbove: false,
  });
  const triggerRef = useRef<HTMLSpanElement>(null);
  const closeTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const calculatePosition = () => {
    if (!triggerRef.current) return;
    const rect = triggerRef.current.getBoundingClientRect();
    const popoverWidth = 330;
    const popoverHeight = 180;

    let left = rect.left + rect.width / 2 - popoverWidth / 2;
    // Horizontal boundary checks
    if (left < 16) left = 16;
    if (left + popoverWidth > window.innerWidth - 16) {
      left = window.innerWidth - popoverWidth - 16;
    }

    // Check if overflowing bottom
    const placeAbove = rect.bottom + popoverHeight > window.innerHeight - 20;
    const top = placeAbove
      ? rect.top - 8
      : rect.bottom + 8;

    setCoords({ top, left, placeAbove });
  };

  const handleMouseEnter = () => {
    if (closeTimeoutRef.current) {
      clearTimeout(closeTimeoutRef.current);
      closeTimeoutRef.current = null;
    }
    calculatePosition();
    setIsOpen(true);
  };

  const handleMouseLeave = () => {
    closeTimeoutRef.current = setTimeout(() => {
      setIsOpen(false);
    }, 200);
  };

  const handleClick = (e: React.MouseEvent) => {
    e.stopPropagation();
    e.preventDefault();
    handleJump(e);
  };

  // Close on window resize or scroll
  useEffect(() => {
    if (!isOpen) return;
    const handleScrollOrResize = () => {
      calculatePosition();
    };
    window.addEventListener('resize', handleScrollOrResize, { passive: true });
    window.addEventListener('scroll', handleScrollOrResize, { passive: true });
    return () => {
      window.removeEventListener('resize', handleScrollOrResize);
      window.removeEventListener('scroll', handleScrollOrResize);
    };
  }, [isOpen]);

  useEffect(() => {
    return () => {
      if (closeTimeoutRef.current) {
        clearTimeout(closeTimeoutRef.current);
      }
    };
  }, []);

  const handleJump = (e: React.MouseEvent) => {
    e.stopPropagation();
    setIsOpen(false);
    if (onJumpToReference) {
      onJumpToReference(id, refItem?.page);
    } else {
      // Fallback
      const el = document.getElementById(`ref-item-${id}`);
      if (el) {
        const rect = el.getBoundingClientRect();
        const top = window.pageYOffset + rect.top - 120;
        window.scrollTo({ top, behavior: 'smooth' });
        el.classList.add('ref-glow-pulse');
        setTimeout(() => el.classList.remove('ref-glow-pulse'), 2500);
      }
    }
  };

  // Clean raw reference text to construct an effective search query
  const cleanRawQuery = (refItem?.raw || '')
    .replace(/^\[\s*\d+\s*\]\s*/, '')
    .replace(/^\d+\.\s*/, '')
    .replace(/\s+/g, ' ')
    .trim();

  const searchQuery = refItem?.title && refItem.title !== `[${id}]`
    ? refItem.title
    : (cleanRawQuery || (refItem?.authors ? `${refItem.authors} ${refItem.year || ''}` : `[${id}]`));

  const scholarUrl = `https://scholar.google.com/scholar?q=${encodeURIComponent(searchQuery)}`;

  const arxivUrl = refItem?.arxivId
    ? `https://arxiv.org/abs/${refItem.arxivId}`
    : `https://arxiv.org/search/?query=${encodeURIComponent(searchQuery)}&searchtype=all`;

  return (
    <span
      ref={triggerRef}
      onMouseEnter={handleMouseEnter}
      onMouseLeave={handleMouseLeave}
      onClick={handleClick}
      className="relative inline-block cursor-pointer"
    >
      {children}

      {/* Render via Portal to document.body to avoid clipping by backdrop-filter or overflow-hidden */}
      {isOpen && typeof document !== 'undefined' && createPortal(
        <div
          style={{
            position: 'fixed',
            top: coords.placeAbove ? 'auto' : `${coords.top}px`,
            bottom: coords.placeAbove ? `${Math.max(16, window.innerHeight - coords.top)}px` : 'auto',
            left: `${coords.left}px`,
            width: '330px',
            zIndex: 99999,
          }}
          onMouseEnter={handleMouseEnter}
          onMouseLeave={handleMouseLeave}
          onClick={(e) => {
            // Stop propagation to prevent React SyntheticEvent from bubbling up to triggerRef's onClick
            e.stopPropagation();
          }}
          className="animate-fade-in liquid-glass-popover rounded-2xl p-4 text-left text-gray-800 pointer-events-auto select-text"
        >
          {/* Header */}
          <div className="flex items-center gap-2 mb-2">
            <span className="inline-flex items-center justify-center font-mono font-bold text-xs px-2 py-0.5 rounded-md bg-violet-600 text-white shadow-xs">
              [{id}]
            </span>
            <span className="text-xs font-semibold text-violet-900 truncate flex-1">
              {refItem?.year ? `${refItem.year} 年文献` : '参考文献引用'}
            </span>
            {refItem?.page && (
              <span className="text-[10px] text-gray-400 bg-gray-100 px-1.5 py-0.5 rounded">
                P.{refItem.page}
              </span>
            )}
          </div>

          {/* Reference Info */}
          {refItem ? (
            <div className="space-y-1.5 text-xs">
              {refItem.title && (
                <div className="font-semibold text-gray-900 leading-snug line-clamp-2">
                  {refItem.title}
                </div>
              )}
              {refItem.authors && (
                <div className="text-gray-600 line-clamp-1 flex items-center gap-1.5">
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="text-violet-500 shrink-0">
                    <path d="M19 21v-2a4 4 0 0 0-4-4H9a4 4 0 0 0-4 4v2" />
                    <circle cx="12" cy="7" r="4" />
                  </svg>
                  <span className="truncate">{refItem.authors}</span>
                </div>
              )}
              {refItem.venueYear && (
                <div className="text-gray-500 text-[11px] italic line-clamp-1">
                  {refItem.venueYear}
                </div>
              )}
              {!refItem.title && (
                <div className="text-gray-700 line-clamp-3 text-[11px] leading-relaxed">
                  {refItem.raw}
                </div>
              )}
            </div>
          ) : (
            <div className="text-xs text-gray-400 italic py-1">
              暂未定位到文末编号为 [{id}] 的条目
            </div>
          )}

          {/* Action Footer */}
          <div className="flex items-center gap-1.5 mt-3 pt-2.5 border-t border-violet-100/80">
            <a
              href={scholarUrl}
              target="_blank"
              rel="noopener noreferrer"
              onClick={(e) => {
                // Allow opening in new tab, but stop bubbling to trigger span
                e.stopPropagation();
              }}
              className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-[11px] font-medium liquid-glass-pill hover:bg-violet-100/90 text-violet-800 transition-all cursor-pointer"
              title="在 Google Scholar 检索此文献"
            >
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M22 10v6M2 10l10-5 10 5-10 5z" />
                <path d="M6 12v5c3 3 9 3 12 0v-5" />
              </svg>
              <span>Google 学术</span>
            </a>

            {arxivUrl && (
              <a
                href={arxivUrl}
                target="_blank"
                rel="noopener noreferrer"
                onClick={(e) => {
                  // Allow opening in new tab, but stop bubbling to trigger span
                  e.stopPropagation();
                }}
                className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-[11px] font-medium bg-red-50/90 hover:bg-red-100 text-red-700 border border-red-200/60 shadow-2xs transition-all cursor-pointer"
                title="在 arXiv 查看论文预印本"
              >
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                  <polyline points="14 2 14 8 20 8" />
                  <line x1="16" y1="13" x2="8" y2="13" />
                  <line x1="16" y1="17" x2="8" y2="17" />
                  <polyline points="10 9 9 9 8 9" />
                </svg>
                <span>arXiv</span>
              </a>
            )}

            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                handleJump(e);
              }}
              className="ml-auto inline-flex items-center gap-1.5 px-3 py-1 rounded-lg text-[11px] font-semibold bg-violet-600 hover:bg-violet-700 active:bg-violet-800 text-white transition-all shadow-xs cursor-pointer"
              title="平滑滚动至文末参考文献"
            >
              <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                <line x1="12" y1="5" x2="12" y2="19" />
                <polyline points="19 12 12 19 5 12" />
              </svg>
              <span>定位原文</span>
            </button>
          </div>
        </div>,
        document.body
      )}
    </span>
  );
};
