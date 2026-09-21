import { useState, useCallback, useRef, useEffect, memo, useMemo, type ReactNode } from 'react';
import katex from 'katex';
import 'katex/dist/katex.min.css';
import {
  uploadPdf, startTranslation, cancelTranslation, getDownloadUrl,
  listHistory, loadHistoryTask, deleteHistoryTask, getOcrModels,
  type HistoryItem, type OcrModelInfo
} from './api';
import { useWebSocket } from './hooks/useWebSocket';
import React from 'react';
import { buildReferenceIndex } from './utils/referenceParser';
import { buildGlobalVariableIndex } from './utils/variableExtractor';
import { InteractiveText } from './components/InteractiveText';
import { EquationCard } from './components/EquationCard';
import { PaperTLDRCard } from './components/PaperTLDRCard';
import { VariableInspectorDrawer } from './components/VariableInspectorDrawer';
import { CodeCard } from './components/CodeCard';
import {
  isCodeBlock,
  isCodeCaption,
  isCodeStart,
  isSectionHeading,
  matchCodeCaption,
} from './utils/codeDetector';
import { sanitizeLatexMath } from './utils/latexSanitizer';
import type { ReferenceItem, PaperTLDR } from './types';

type AppMode = 'upload' | 'translating' | 'done';
interface TaskInfo {
  task_id: string; filename: string;
  status: string; page_count: number;
  ocr_model?: string;
  quality: { total_blocks: number; pass_rate: string } | null;
}
interface BlockData {
  page: number; idx: number; type: string;
  en: string; zh: string; verified?: boolean;
  passthrough?: boolean; bbox?: number[];
  figure_id?: string;
}

/* ═══ SVG Icons ═══ */
const IconUpload = () => (
  <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
    <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
    <polyline points="17 8 12 3 7 8" /><line x1="12" y1="3" x2="12" y2="15" />
  </svg>
);
const IconFile = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
    <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
    <polyline points="14 2 14 8 20 8" />
  </svg>
);
const IconDownload = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
    <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
    <polyline points="7 10 12 15 17 10" /><line x1="12" y1="15" x2="12" y2="3" />
  </svg>
);
const IconRefresh = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
    <polyline points="23 4 23 10 17 10" /><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10" />
  </svg>
);
const IconCheck = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <polyline points="20 6 9 17 4 12" />
  </svg>
);
const IconAlert = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <circle cx="12" cy="12" r="10" /><line x1="12" y1="8" x2="12" y2="12" /><line x1="12" y1="16" x2="12.01" y2="16" />
  </svg>
);
const IconClose = () => (
  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
    <line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" />
  </svg>
);
const IconPage = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
    <rect x="3" y="3" width="18" height="18" rx="2" ry="2" /><line x1="3" y1="9" x2="21" y2="9" />
  </svg>
);
const IconLock = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <rect x="3" y="11" width="18" height="11" rx="2" ry="2" /><path d="M7 11V7a5 5 0 0 1 10 0v4" />
  </svg>
);
const IconUnlock = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <rect x="3" y="11" width="18" height="11" rx="2" ry="2" /><path d="M7 11V7a5 5 0 0 1 9.9-1" />
  </svg>
);

/* ─── Decorative blobs ─── */
function DecoBlobs() {
  return (
    <div className="absolute inset-0 overflow-hidden pointer-events-none select-none">
      <div className="absolute -top-24 -left-24 w-80 h-80 rounded-full opacity-[0.07] animate-float"
           style={{ background: 'linear-gradient(135deg, #8b7fc7, #a89cc8)' }} />
      <div className="absolute top-1/3 -right-20 w-64 h-64 rounded-full opacity-[0.05] animate-float-d1"
           style={{ background: 'linear-gradient(135deg, #9b8ec4, #c4b8e0)' }} />
      <div className="absolute -bottom-16 left-1/3 w-72 h-72 rounded-full opacity-[0.04] animate-float-d2"
           style={{ background: 'linear-gradient(135deg, #a89cc8, #8b7fc7)' }} />
    </div>
  );
}



/* ═══════════════════════════════════════════════
   StreamReveal — CSS 揭示动画，保留 KaTeX 渲染
   速度：1ms/字（文本总长 = 动画毫秒数）
   ═══════════════════════════════════════════════ */
const StreamReveal = memo(({ children, textLen }: { children: ReactNode; textLen: number }) => {
  const duration = Math.max(300, Math.min(textLen * 1, 3000));
  return (
    <span className="stream-reveal" style={{ animationDuration: `${duration}ms` }}>
      {children}
    </span>
  );
});

/* ═══════════════════════════════════════════════
   Main App
   ═══════════════════════════════════════════════ */
export default function App() {
  const [mode, setMode] = useState<AppMode>('upload');
  const [task, setTask] = useState<TaskInfo | null>(null);
  const [blocks, setBlocks] = useState<BlockData[]>([]);
  const [currentPage, setCurrentPage] = useState(0);
  const [totalPages, setTotalPages] = useState(0);
  const [error, setError] = useState('');
  const [activePage, setActivePage] = useState(1);
  const [locked, setLocked] = useState(false);
  const [compareMode, setCompareMode] = useState(false);
  const [phase, setPhase] = useState<'ocr' | 'translate'>('ocr');
  const [ocrPage, setOcrPage] = useState(0);
  const [transDone, setTransDone] = useState(0);
  const [transTotal, setTransTotal] = useState(0);
  const [history, setHistory] = useState<HistoryItem[]>([]);
  const [selectedOcrModel, setSelectedOcrModel] = useState<string>('unlimited');
  const [ocrModels, setOcrModels] = useState<OcrModelInfo[]>([]);
  const [tldr, setTldr] = useState<PaperTLDR | null>(null);
  const [isTLDRLoading, setIsTLDRLoading] = useState(false);
  const [isVarDrawerOpen, setIsVarDrawerOpen] = useState(false);
  const blocksRef = useRef<BlockData[]>([]);
  const mainRef = useRef<HTMLDivElement>(null);

  /* ── 加载历史记录与可用 OCR 模型 ── */
  useEffect(() => {
    let retries = 0;
    let timer: any = null;

    const loadInitialData = () => {
      listHistory()
        .then(data => {
          if (data && data.length > 0) {
            setHistory(data);
          } else if (retries < 5) {
            retries++;
            timer = setTimeout(loadInitialData, 1500);
          }
        })
        .catch(() => {
          if (retries < 5) {
            retries++;
            timer = setTimeout(loadInitialData, 1500);
          }
        });

      getOcrModels()
        .then(models => {
          if (models && models.length > 0) {
            setOcrModels(models);
            const def = models.find(m => m.is_default);
            if (def) setSelectedOcrModel(def.id);
          }
        })
        .catch(() => {});
    };

    loadInitialData();
    return () => {
      if (timer) clearTimeout(timer);
    };
  }, []);

  const loadHistory = async (taskId: string) => {
    setError('');
    try {
      const data = await loadHistoryTask(taskId);
      setTask(data);
      setTotalPages(data.page_count);
      setCurrentPage(data.page_count);
      setBlocks(data.blocks || []);
      blocksRef.current = data.blocks || [];
      if (data.tldr && Object.keys(data.tldr).length > 0) {
        setTldr(data.tldr);
        setIsTLDRLoading(false);
      } else {
        setTldr(null);
        setIsTLDRLoading(true);
        fetch(`http://localhost:7860/api/task/${taskId}/tldr`)
          .then(res => res.json())
          .then(resData => {
            if (resData?.tldr && Object.keys(resData.tldr).length > 0) {
              setTldr(resData.tldr);
            }
          })
          .catch(() => {})
          .finally(() => {
            setIsTLDRLoading(false);
          });
      }
      setMode('done');
      setLocked(true);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Failed to load history');
    }
  };

  const removeHistory = async (taskId: string) => {
    try {
      await deleteHistoryTask(taskId);
      setHistory(prev => prev.filter(h => h.task_id !== taskId));
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Failed to delete');
    }
  };

  /* ── 防刷新保护：有任务就拦截 ── */
  useEffect(() => {
    if (mode === 'upload') return;
    const beforeUnload = (e: BeforeUnloadEvent) => {
      e.preventDefault();
      e.returnValue = '翻译内容将丢失';
    };
    const pageHide = (e: PageTransitionEvent) => {
      if (e.persisted) return;
      e.preventDefault();
    };
    window.addEventListener('beforeunload', beforeUnload, true);
    window.addEventListener('pagehide', pageHide, true);
    return () => {
      window.removeEventListener('beforeunload', beforeUnload, true);
      window.removeEventListener('pagehide', pageHide, true);
    };
  }, [mode]);

  /* 翻译完成自动加锁 */
  useEffect(() => {
    if (mode === 'done') setLocked(true);
  }, [mode]);

  const clear = () => {
    setMode('upload'); setTask(null); setBlocks([]);
    setCurrentPage(0); setTotalPages(0); setError('');
    setLocked(false); blocksRef.current = [];
    setPhase('ocr'); setOcrPage(0); setTransDone(0); setTransTotal(0);
    setTldr(null); setIsTLDRLoading(false); setIsVarDrawerOpen(false);
  };

  const onWsEvent = useCallback((e: Record<string, unknown>) => {
    switch (e.type) {
      case 'start':
        setTotalPages(e.total_pages as number);
        if (e.ocr_model) {
          setTask(prev => prev ? { ...prev, ocr_model: e.ocr_model as string } : prev);
        }
        break;
      case 'phase': {
        const ph = e.phase as 'ocr' | 'translate';
        setPhase(ph);
        if (ph === 'translate') setIsTLDRLoading(true);
        if (e.total_blocks) setTransTotal(e.total_blocks as number);
        break;
      }
      case 'tldr': {
        if (e.tldr) {
          setTldr(e.tldr as PaperTLDR);
          setIsTLDRLoading(false);
        }
        break;
      }
      case 'ocr_progress':
        setOcrPage(e.page as number);
        setCurrentPage(e.page as number);
        break;
      case 'translate_progress':
        setTransDone(e.done as number);
        setTransTotal(e.total as number);
        break;
      case 'page_start': setCurrentPage(e.page as number); break;
      case 'ocr_page_blocks': {
        const pageBlocks = (e.blocks as BlockData[]) || [];
        const existingKeys = new Set(blocksRef.current.map(b => `${b.page}-${b.idx}`));
        const toAdd: BlockData[] = [];
        for (const b of pageBlocks) {
          const key = `${b.page}-${b.idx}`;
          if (!existingKeys.has(key)) {
            toAdd.push({
              page: b.page,
              idx: b.idx,
              type: b.type,
              en: b.en,
              zh: b.zh || (b.passthrough ? b.en : ''),
              figure_id: b.figure_id || '',
              bbox: b.bbox,
              verified: true,
              passthrough: b.passthrough || ['ref_text','equation','table',
                             'aside_text','header','footer',
                             'title','algorithm'].includes(b.type)
                             || !['text','image_caption','image_footnote','image'].includes(b.type),
            });
            existingKeys.add(key);
          }
        }
        if (toAdd.length > 0) {
          blocksRef.current = [...blocksRef.current, ...toAdd];
          setBlocks([...blocksRef.current]);
        }
        break;
      }
      case 'block_done': {
        const btype = e.block_type as string;
        const page = e.page as number;
        const idx = e.idx as number;
        const bData: BlockData = {
          page, idx, type: btype,
          en: e.en as string, zh: e.zh as string,
          verified: e.verified !== false,
          figure_id: (e.figure_id as string) || '',
          passthrough: ['ref_text','equation','table',
                         'aside_text','header','footer',
                         'title','algorithm'].includes(btype)
                         || !['text','image_caption','image_footnote','image'].includes(btype),
        };
        const existingIdx = blocksRef.current.findIndex(item => item.page === page && item.idx === idx);
        if (existingIdx >= 0) {
          blocksRef.current = blocksRef.current.map((item, i) =>
            i === existingIdx ? { ...item, ...bData } : item
          );
        } else {
          blocksRef.current = [...blocksRef.current, bData];
        }
        setBlocks([...blocksRef.current]);
        break;
      }
      case 'figure': {
        const figId = e.figure_id as string;
        const page = e.page as number;
        const idx = e.idx as number;
        if (figId) {
          blocksRef.current = blocksRef.current.map(item =>
            (item.page === page && item.idx === idx) ? { ...item, figure_id: figId } : item
          );
          setBlocks([...blocksRef.current]);
        }
        break;
      }
      case 'complete': {
        setMode('done');
        setIsTLDRLoading(false);
        const q = (e.quality as { total_blocks: number; pass_rate: string }) || null;
        setTask(prev => prev ? {
          ...prev,
          status: 'completed',
          quality: q || { total_blocks: blocksRef.current.length, pass_rate: '100%' }
        } : prev);
        break;
      }
      case 'error': {
        setError(e.message as string);
        setIsTLDRLoading(false);
        break;
      }
    }
  }, []);

  useWebSocket(task?.task_id ?? null, onWsEvent);

  /* ── 滚动追踪当前页 ── */
  useEffect(() => {
    if (!mainRef.current || mode === 'upload') return;
    const el = mainRef.current;
    const observer = new IntersectionObserver(
      entries => { for (const e of entries) { if (e.isIntersecting) { const p = Number(e.target.getAttribute('data-page')); if (p) setActivePage(p); } } },
      { root: null, threshold: 0.15, rootMargin: '-16px 0px -60% 0px' }
    );
    el.querySelectorAll('[data-page]').forEach(n => observer.observe(n));
    return () => observer.disconnect();
  }, [blocks.length, mode]);

  const scrollToPage = useCallback((page: number) => {
    setActivePage(page);
    const el = mainRef.current?.querySelector(`[data-page="${page}"]`);
    el?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }, []);

  const refIndex = useMemo(() => buildReferenceIndex(blocks), [blocks]);
  const globalVariables = useMemo(() => buildGlobalVariableIndex(blocks), [blocks]);

  const handleJumpToEquation = useCallback((page: number, blockIdx: number) => {
    setActivePage(page);
    const el = document.getElementById(`eq-item-p${page}-i${blockIdx}`);
    if (el) {
      const rect = el.getBoundingClientRect();
      const top = window.pageYOffset + rect.top - 120;
      window.scrollTo({ top, behavior: 'smooth' });
      el.classList.add('ref-glow-pulse');
      setTimeout(() => el.classList.remove('ref-glow-pulse'), 2500);
    } else {
      scrollToPage(page);
      setTimeout(() => {
        const elRetry = document.getElementById(`eq-item-p${page}-i${blockIdx}`);
        if (elRetry) {
          const rect = elRetry.getBoundingClientRect();
          const top = window.pageYOffset + rect.top - 120;
          window.scrollTo({ top, behavior: 'smooth' });
          elRetry.classList.add('ref-glow-pulse');
          setTimeout(() => elRetry.classList.remove('ref-glow-pulse'), 2500);
        }
      }, 350);
    }
  }, [scrollToPage]);

  const handleJumpToReference = useCallback((id: string, page?: number) => {
    const targetPage = page || (refIndex[id]?.page);
    if (targetPage) {
      setActivePage(targetPage);
    }
    const el = document.getElementById(`ref-item-${id}`);
    if (el) {
      el.scrollIntoView({ behavior: 'smooth', block: 'start' });
      el.classList.add('ref-glow-pulse');
      setTimeout(() => el.classList.remove('ref-glow-pulse'), 2500);
    } else if (targetPage) {
      scrollToPage(targetPage);
      setTimeout(() => {
        const elRetry = document.getElementById(`ref-item-${id}`);
        if (elRetry) {
          elRetry.scrollIntoView({ behavior: 'smooth', block: 'start' });
          elRetry.classList.add('ref-glow-pulse');
          setTimeout(() => elRetry.classList.remove('ref-glow-pulse'), 2500);
        }
      }, 350);
    }
  }, [scrollToPage, refIndex]);

  const handleOpenVariableInspector = useCallback(() => {
    setIsVarDrawerOpen(true);
  }, []);

  const handleUpload = async (file: File) => {
    setError('');
    try {
      const info = await uploadPdf(file);
      setTask({ ...info, ocr_model: selectedOcrModel });
      setTotalPages(info.page_count);
      setMode('translating');
      await startTranslation(info.task_id, 144, 0, null, selectedOcrModel);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Upload failed');
    }
  };

  const showSidebar = mode !== 'upload' && (task?.page_count ?? 0) > 0;

  return (
    <div className="min-h-screen">
      {/* ── Header ── */}
      <header className="sticky top-0 z-50 border-b border-white/50 bg-white/55 backdrop-blur-[45px] saturate-[1.85] shadow-[0_4px_24px_-4px_rgba(139,127,199,0.1),inset_0_1.5px_0_rgba(255,255,255,0.9)]">
        <div className="max-w-[95rem] mx-auto px-6 py-1 flex items-end justify-between">
          <div className="flex items-end gap-2.5">
            <img src="/logo.jpg" alt="logo" className="w-20 h-20 rounded-full object-cover border-2 border-white/60 shadow-sm -mb-8" />
            <span className="font-semibold text-gray-900 tracking-tight mb-1">LunePaper</span>
          </div>

          <div className="flex items-center gap-3">
            {task && mode !== 'upload' && (
              <>
                <span className="text-gray-500 flex items-center gap-1.5 text-sm"><IconFile />{task.filename}</span>
                <span className="text-gray-300">·</span>
                <span className="text-gray-500 text-sm">{task.page_count} 页</span>
                {task.ocr_model && (
                  <>
                    <span className="text-gray-300">·</span>
                    <span className="text-violet-700 font-medium text-xs liquid-glass-pill px-2.5 py-0.5 rounded-full">
                      {task.ocr_model === 'ovis' ? 'OvisOCR2' : 'Unlimited-OCR'}
                    </span>
                  </>
                )}
                {mode === 'done' && (
                  <span className="inline-flex items-center gap-1 text-emerald-700 bg-emerald-100/80 border border-emerald-200/60 shadow-2xs px-2.5 py-0.5 rounded-full text-xs font-medium">
                    <IconCheck /> 完成
                  </span>
                )}
              </>
            )}

            {/* ── 保护锁按钮 ── */}
            {mode !== 'upload' && (
              <button
                onClick={() => setLocked(l => !l)}
                title={locked ? '已保护 · 刷新将提示确认' : '未保护 · 刷新将丢失内容'}
                className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-medium transition-all cursor-pointer
                  ${locked
                    ? 'bg-violet-100/90 text-violet-700 border border-violet-200/80 shadow-2xs'
                    : 'liquid-glass-pill text-gray-500 hover:text-gray-700'
                  }`}
              >
                {locked ? <IconLock /> : <IconUnlock />}
                {locked ? '已保护' : '未保护'}
              </button>
            )}

            {/* ── 对照模式按钮 ── */}
            {mode !== 'upload' && (
              <button
                onClick={() => setCompareMode(c => !c)}
                title={compareMode ? '关闭 PDF 对照' : '开启 PDF 对照'}
                className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-medium transition-all cursor-pointer
                  ${compareMode
                    ? 'bg-violet-100/90 text-violet-700 border border-violet-200/80 shadow-2xs'
                    : 'liquid-glass-pill text-gray-500 hover:text-gray-700'
                  }`}
              >
                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <rect x="2" y="3" width="20" height="18" rx="2" /><line x1="12" y1="3" x2="12" y2="21" />
                </svg>
                对照
              </button>
            )}

            {/* ── 符号字典按钮 ── */}
            {mode !== 'upload' && globalVariables.length > 0 && (
              <button
                type="button"
                onClick={handleOpenVariableInspector}
                title="打开全篇数学公式变量字典与符号追踪抽屉"
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-medium liquid-glass-pill text-violet-800 hover:bg-violet-100/90 transition-all cursor-pointer"
              >
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="text-violet-600">
                  <path d="M4 19.5v-15A2.5 2.5 0 0 1 6.5 2H20v20H6.5a2.5 2.5 0 0 1-2.5-2.5Z" />
                  <path d="M6 10h10" />
                  <path d="M6 14h10" />
                </svg>
                <span>符号字典</span>
                <span className="text-[10px] font-bold px-1.5 py-0.2 rounded-full bg-violet-100/80 text-violet-700">
                  {globalVariables.length}
                </span>
              </button>
            )}
          </div>
        </div>
      </header>

      {/* ── Upload ── */}
      {mode === 'upload' && (
        <UploadView
          onUpload={handleUpload}
          error={error}
          history={history}
          onLoadHistory={loadHistory}
          onDeleteHistory={removeHistory}
          selectedOcrModel={selectedOcrModel}
          onSelectOcrModel={setSelectedOcrModel}
          ocrModels={ocrModels}
        />
      )}

      {/* ── Translating / Done ── */}
      {(mode === 'translating' || mode === 'done') && (
        <div className="max-w-[95rem] mx-auto px-6 py-6">
          {/* Progress — two phases: OCR then Translate */}
          {/* Progress — two phases: OCR then Translate (Sticky top-14) */}
          {mode === 'translating' && (
            <div className="sticky top-14 z-40 mb-5 liquid-glass-card animate-fade-in-up rounded-2xl px-5 py-3.5">
              <div className="flex items-center justify-between gap-5">
                <div className="flex-1">
                  {phase === 'ocr' ? (
                    /* ── OCR 阶段 ── */
                    <>
                      <div className="flex justify-between text-sm mb-2">
                        <span className="text-gray-600 flex items-center gap-2 font-medium">
                          <span className="relative flex h-2.5 w-2.5">
                            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-violet-400 opacity-75" />
                            <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-violet-500" />
                          </span>
                          OCR 识别中...
                        </span>
                        <span className="text-gray-500 font-medium tabular-nums">
                          {ocrPage} / {totalPages} 页
                          <span className="ml-2 text-violet-600 font-semibold">
                            {totalPages > 0 ? Math.round((ocrPage / totalPages) * 100) : 0}%
                          </span>
                        </span>
                      </div>
                      <div className="h-2.5 bg-violet-100/40 rounded-full overflow-hidden relative shadow-inner">
                        <div className="h-full rounded-full transition-all duration-500 ease-out progress-stripe relative"
                             style={{ width: `${totalPages > 0 ? (ocrPage / totalPages) * 100 : 0}%`,
                                      background: 'linear-gradient(90deg, #7c6cb8, #9b8ec4)' }}>
                          <div className="absolute right-0 top-1/2 -translate-y-1/2 w-3 h-3 bg-white rounded-full shadow-md border-2 border-violet-400" />
                        </div>
                      </div>
                    </>
                  ) : (
                    /* ── 翻译阶段 ── */
                    <>
                      <div className="flex justify-between text-sm mb-2">
                        <span className="text-gray-600 flex items-center gap-2 font-medium">
                          <span className="relative flex h-2.5 w-2.5">
                            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-violet-400 opacity-75" />
                            <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-violet-500" />
                          </span>
                          翻译中...
                        </span>
                        <span className="text-gray-500 font-medium tabular-nums">
                          {transDone} / {transTotal} 块
                          <span className="ml-2 text-violet-600 font-semibold">
                            {transTotal > 0 ? Math.round((transDone / transTotal) * 100) : 0}%
                          </span>
                        </span>
                      </div>
                      <div className="h-2.5 bg-violet-100/40 rounded-full overflow-hidden relative shadow-inner">
                        <div className="h-full rounded-full transition-all duration-500 ease-out progress-stripe relative"
                             style={{ width: `${transTotal > 0 ? (transDone / transTotal) * 100 : 0}%`,
                                      background: 'linear-gradient(90deg, #7c6cb8, #9b8ec4)' }}>
                          <div className="absolute right-0 top-1/2 -translate-y-1/2 w-3 h-3 bg-white rounded-full shadow-md border-2 border-violet-400" />
                        </div>
                      </div>
                    </>
                  )}
                </div>
                <button
                  onClick={async () => {
                    if (confirm('确定要取消当前任务吗？已翻译的临时内容将被中止。')) {
                      if (task) {
                        try { await cancelTranslation(task.task_id); } catch {}
                      }
                      clear();
                    }
                  }}
                  className="shrink-0 inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-rose-600 hover:text-rose-700 bg-rose-50/90 hover:bg-rose-100 rounded-xl transition-all border border-rose-200/60 shadow-2xs cursor-pointer active:scale-95"
                  title="取消当前翻译任务并释放 GPU 显存"
                >
                  <IconClose /> 取消任务
                </button>
              </div>
            </div>
          )}

          {/* Done bar with Interactive Page Seeking Slider (Sticky top-14 with Liquid Glass 2.0) */}
          {mode === 'done' && (
            <div className="sticky top-14 z-40 mb-5 liquid-glass-card animate-fade-in-up rounded-2xl px-5 py-3 flex items-center gap-4">
              <div className="flex-1 flex items-center gap-3 min-w-0">
                <span className="text-xs font-semibold text-violet-800 liquid-glass-pill px-3 py-1 rounded-full whitespace-nowrap shadow-xs">
                  第 {activePage} / {totalPages || task?.page_count || 1} 页
                </span>
                <input
                  type="range"
                  min={1}
                  max={totalPages || task?.page_count || 1}
                  value={activePage}
                  onChange={(e) => scrollToPage(Number(e.target.value))}
                  className="flex-1 h-2 bg-violet-100/90 rounded-lg appearance-none cursor-pointer accent-violet-600 hover:accent-violet-700 transition-all"
                  title="滑动快速调节当前阅读页码"
                />
              </div>
              <span className="text-xs text-gray-500 whitespace-nowrap hidden sm:inline font-medium">
                {task?.quality?.total_blocks ?? blocks.length} 个内容块
              </span>
              <button onClick={() => window.open(getDownloadUrl(task!.task_id))}
                title="下载双语 Markdown 与配图压缩包 (ZIP)"
                className="inline-flex items-center gap-1.5 px-3.5 py-2 text-white rounded-xl text-xs font-semibold
                           transition-all hover:shadow-md hover:shadow-violet-300/40 hover:-translate-y-0.5 active:translate-y-0 shrink-0 cursor-pointer"
                style={{ background: 'linear-gradient(135deg, #7c6cb8, #9b8ec4)' }}>
                <IconDownload /> 下载 ZIP
              </button>
              <button onClick={() => { if (locked) { if (!confirm('确定要开始新任务吗？当前翻译内容将丢失。')) return; } clear(); }}
                className="inline-flex items-center gap-1.5 px-3 py-2 text-gray-700 liquid-glass-pill rounded-xl text-xs font-medium hover:text-violet-800 transition-all cursor-pointer shrink-0">
                <IconRefresh /> 新任务
              </button>
            </div>
          )}

          {/* Error */}
          {error && (
            <div className="mb-4 p-3 bg-red-50 border border-red-100 rounded-lg text-red-600 text-sm flex items-center gap-2">
              <IconAlert /> {error}
            </div>
          )}

          {/* ── Layout: sidebar + content [+ pdf panel] ── */}
          <div className="flex gap-5">
            {/* 左侧页缩略图导航 */}
            {showSidebar && (
              <div className="hidden lg:block w-36 shrink-0">
                <div className="sticky top-32 max-h-[calc(100vh-8.5rem)] overflow-y-auto sidebar-scroll">
                  <PageSidebar
                    totalPages={totalPages || task?.page_count || 0}
                    activePage={activePage}
                    currentPage={currentPage}
                    taskId={task?.task_id ?? ''}
                    onGoToPage={scrollToPage}
                  />
                </div>
              </div>
            )}

            {/* 主内容区（翻译） */}
            <div ref={mainRef} className={`min-w-0 ${compareMode ? 'w-3/5' : 'flex-1'}`}>
              <Preview
                blocks={blocks}
                taskId={task?.task_id ?? ''}
                phase={phase}
                refIndex={refIndex}
                onJumpToReference={handleJumpToReference}
                tldr={tldr}
                isTLDRLoading={isTLDRLoading}
                onOpenVariableInspector={handleOpenVariableInspector}
              />
            </div>

            {/* 右侧 PDF 对照面板 */}
            {compareMode && task && (
              <div className="w-2/5 shrink-0">
                <div className="sticky top-32 max-h-[calc(100vh-8.5rem)] overflow-y-auto sidebar-scroll rounded-xl border border-white/30 bg-white/50 backdrop-blur-[40px] saturate-[1.6] shadow-[0_2px_8px_rgba(0,0,0,0.06),inset_0_1px_0_rgba(255,255,255,0.5)]">
                  <div className="sticky top-0 z-30 bg-white/90 border-b border-white/30 px-3 py-2 backdrop-blur-sm">
                    <div className="flex items-center justify-between">
                      <span className="text-xs font-medium text-gray-400">原文 · 第 {activePage} 页</span>
                      <div className="flex items-center gap-1">
                        <button onClick={() => { if (activePage > 1) scrollToPage(activePage - 1); }}
                          disabled={activePage <= 1}
                          className="p-1 rounded hover:bg-white/50 disabled:opacity-30 transition-colors text-gray-500">
                          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><polyline points="15 18 9 12 15 6" /></svg>
                        </button>
                        <span className="text-[10px] text-gray-300 px-1">{activePage}/{totalPages || task.page_count}</span>
                        <button onClick={() => { if (activePage < (totalPages || task.page_count)) scrollToPage(activePage + 1); }}
                          disabled={activePage >= (totalPages || task.page_count)}
                          className="p-1 rounded hover:bg-white/50 disabled:opacity-30 transition-colors text-gray-500">
                          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><polyline points="9 18 15 12 9 6" /></svg>
                        </button>

                      </div>
                    </div>
                  </div>
                  <img
                    src={`http://localhost:7860/api/page-image/${task.task_id}/${activePage}?dpi=150`}
                    alt={`Page ${activePage}`}
                    className="w-full"
                  />
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* ── 全篇公式变量全局追踪侧边抽屉 ── */}
      <VariableInspectorDrawer
        isOpen={isVarDrawerOpen}
        onClose={() => setIsVarDrawerOpen(false)}
        variables={globalVariables}
        onJumpToEquation={handleJumpToEquation}
      />
    </div>
  );
}

/* ═══════════════════════════════════════════ */
/*  Page Sidebar                              */
/* ═══════════════════════════════════════════ */
function PageSidebar({
  totalPages, activePage, currentPage, taskId, onGoToPage,
}: {
  totalPages: number; activePage: number; currentPage: number;
  taskId: string; onGoToPage: (p: number) => void;
}) {
  if (totalPages === 0) return null;
  return (
    <div className="overflow-y-auto max-h-full sidebar-scroll pr-1">
      <div className="text-[10px] font-semibold text-gray-400 uppercase tracking-widest mb-2 px-0.5">页面</div>
      <div className="space-y-1.5">
        {Array.from({ length: totalPages }, (_, i) => {
          const p = i + 1;
          const isActive = p === activePage;
          const isReached = p <= currentPage;
          return (
            <button key={p} onClick={() => onGoToPage(p)}
              className={`group w-full rounded-lg overflow-hidden transition-all duration-200 text-left
                bg-white/40 backdrop-blur-sm border border-white/30
                ${isActive ? 'ring-2 ring-violet-400 shadow-md shadow-violet-100 bg-white/60' : 'hover:ring-violet-200 hover:shadow-sm hover:bg-white/50'}`}
            >
              <div className="relative bg-gray-50 aspect-[3/4] overflow-hidden">
                {isReached ? (
                  <img src={`http://localhost:7860/api/page-image/${taskId}/${p}`}
                       alt={`Page ${p}`} className="w-full h-full object-cover object-top" loading="lazy" />
                ) : (
                  <div className="w-full h-full flex items-center justify-center text-gray-300"><IconPage /></div>
                )}
                {isActive && <div className="absolute inset-0 bg-violet-500/10" />}
              </div>
              <div className={`text-center py-0.5 text-[11px] font-medium transition-colors
                ${isActive ? 'text-violet-600 bg-violet-50' : 'text-gray-400 group-hover:text-gray-600'}`}>
                {p}
              </div>
            </button>
          );
        })}
      </div>
    </div>
  );
}

/* ═══════════════════════════════════════════ */
/*  Upload View                               */
/* ═══════════════════════════════════════════ */
function UploadView({
  onUpload, error, history, onLoadHistory, onDeleteHistory,
  selectedOcrModel, onSelectOcrModel, ocrModels
}: {
  onUpload: (f: File) => void; error: string;
  history: HistoryItem[];
  onLoadHistory: (taskId: string) => void;
  onDeleteHistory: (taskId: string) => void;
  selectedOcrModel: string;
  onSelectOcrModel: (m: string) => void;
  ocrModels: OcrModelInfo[];
}) {
  const [drag, setDrag] = useState(false);
  const isOvisAvailable = ocrModels.length === 0 || (ocrModels.find(m => m.id === 'ovis')?.available ?? true);
  const isUnlimitedAvailable = ocrModels.length === 0 || (ocrModels.find(m => m.id === 'unlimited')?.available ?? true);

  return (
    <div className="relative flex flex-col items-center justify-center min-h-[calc(100vh-5rem)] px-6">
      <DecoBlobs />
      <div className="relative z-10 max-w-xl w-full animate-fade-in-up">
        <div className="text-center mb-6">
          <h1 className="text-5xl font-extrabold tracking-tight mb-1 drop-shadow-[0_2px_8px_rgba(139,127,199,0.25)]"
              style={{ fontFamily: '"Caveat", cursive' }}><span className="text-gradient">LunePaper</span></h1>
        </div>

        {/* ── OCR 底座选择卡片 ── */}
        <div className="mb-4 liquid-glass-card rounded-2xl p-4 shadow-sm flex flex-col gap-2.5">
          <div className="flex items-center justify-between px-1">
            <span className="text-xs font-semibold text-gray-700 flex items-center gap-1.5">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="text-violet-600">
                <rect x="2" y="3" width="20" height="14" rx="2" /><line x1="8" y1="21" x2="16" y2="21" /><line x1="12" y1="17" x2="12" y2="21" />
              </svg>
              OCR 底座引擎选择:
            </span>
            <span className="text-[11px] text-gray-400 font-mono">
              {selectedOcrModel === 'ovis' ? 'Qwen-VL · n_ctx 8192 · VRAM ~1.7G' : 'DeepSeek2-OCR · n_ctx 8192 · VRAM ~6.0G'}
            </span>
          </div>

          <div className="grid grid-cols-2 gap-2.5">
            <button
              type="button"
              disabled={!isUnlimitedAvailable}
              onClick={() => onSelectOcrModel('unlimited')}
              className={`px-3.5 py-2.5 rounded-xl text-left transition-all border ${
                selectedOcrModel === 'unlimited'
                  ? 'liquid-glass-pill bg-violet-100/80 border-violet-300 ring-2 ring-violet-400/40 shadow-xs'
                  : 'bg-white/50 border-white/60 hover:bg-white/80 hover:border-violet-200 text-gray-600'
              } ${!isUnlimitedAvailable ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer'}`}
            >
              <div className="flex items-center justify-between">
                <span className="text-xs font-bold text-gray-800">Unlimited-OCR</span>
                <span className="text-[10px] font-semibold text-violet-700 bg-violet-100/90 px-1.5 py-0.5 rounded border border-violet-200/60 shadow-2xs">3B MoE</span>
              </div>
              <p className="text-[11px] text-gray-500 mt-0.5 truncate font-mono">
                {isUnlimitedAvailable ? '64×550M · Q8_0 · VRAM ~6.0G' : '未检测到模型文件'}
              </p>
            </button>

            <button
              type="button"
              disabled={!isOvisAvailable}
              onClick={() => onSelectOcrModel('ovis')}
              className={`px-3.5 py-2.5 rounded-xl text-left transition-all border ${
                selectedOcrModel === 'ovis'
                  ? 'liquid-glass-pill bg-violet-100/80 border-violet-300 ring-2 ring-violet-400/40 shadow-xs'
                  : 'bg-white/50 border-white/60 hover:bg-white/80 hover:border-violet-200 text-gray-600'
              } ${!isOvisAvailable ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer'}`}
            >
              <div className="flex items-center justify-between">
                <span className="text-xs font-bold text-gray-800">OvisOCR2</span>
                <span className="text-[10px] font-semibold text-emerald-700 bg-emerald-100/90 px-1.5 py-0.5 rounded border border-emerald-200/60 shadow-2xs">0.8B Dense</span>
              </div>
              <p className="text-[11px] text-gray-500 mt-0.5 truncate font-mono">
                {isOvisAvailable ? '752M · Q8_0 · VRAM ~1.7G' : '未检测到模型文件'}
              </p>
            </button>
          </div>
        </div>

        <div
          onDragOver={e => { e.preventDefault(); setDrag(true); }}
          onDragLeave={() => setDrag(false)}
          onDrop={e => { e.preventDefault(); setDrag(false); const f = e.dataTransfer.files[0]; if (f?.name.endsWith('.pdf')) onUpload(f); }}
          className={`upload-zone rounded-3xl p-10 text-center cursor-pointer transition-all
            ${drag ? 'dragging' : ''}`}
          onClick={() => document.getElementById('fileInput')?.click()}>
          <div className={`mx-auto w-16 h-16 rounded-2xl flex items-center justify-center mb-4 transition-all
            ${drag ? 'bg-violet-100 text-violet-600 scale-110 shadow-md' : 'bg-white/70 text-violet-400 shadow-xs'}`}>
            <IconUpload />
          </div>
          <p className="text-gray-700 text-base font-semibold mb-1">{drag ? '松开以上传' : '拖拽 PDF 到此处'}</p>
          <p className="text-gray-400 text-sm">或点击选择文件</p>
        </div>
        <input id="fileInput" type="file" accept=".pdf" className="hidden"
          onChange={e => { const f = e.target.files?.[0]; if (f) onUpload(f); }} />
        {error && (
          <div className="mt-4 p-3 bg-red-50 border border-red-100 rounded-lg text-red-600 text-sm text-center flex items-center justify-center gap-2 animate-fade-in">
            <IconAlert /> {error}
          </div>
        )}

        {/* ── 历史翻译文献 ── */}
        {history.length > 0 && (
          <div className="mt-8">
            <div className="flex items-center gap-2 mb-3">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="text-violet-400">
                <circle cx="12" cy="12" r="10" /><polyline points="12 6 12 12 16 14" />
              </svg>
              <span className="text-sm font-semibold text-gray-500">历史翻译</span>
              <span className="text-xs text-gray-300 ml-auto">{history.length} 篇</span>
            </div>
            <div className="space-y-2 max-h-64 overflow-y-auto sidebar-scroll pr-1">
              {history.map(item => (
                <div key={item.task_id}
                  className="group flex items-center gap-3 px-4 py-2.5 rounded-xl liquid-glass-pill hover:bg-white/90 hover:border-violet-300/70 transition-all cursor-pointer shadow-2xs"
                  onClick={() => onLoadHistory(item.task_id)}>
                  <div className="flex-1 min-w-0">
                    <div className="text-sm font-medium text-gray-700 truncate">{item.filename}</div>
                    <div className="text-xs text-gray-400 mt-0.5">
                      {item.page_count} 页
                      {item.quality?.total_blocks ? ` · ${item.quality.total_blocks} 块` : ''}
                      {item.quality?.pass_rate ? ` · 通过率 ${item.quality.pass_rate}` : ''}
                      <span className="ml-2">{new Date(item.created_at * 1000).toLocaleDateString('zh-CN')}</span>
                    </div>
                  </div>
                  <button onClick={e => { e.stopPropagation(); if (confirm(`确定删除「${item.filename}」的翻译记录？`)) onDeleteHistory(item.task_id); }}
                    className="opacity-0 group-hover:opacity-100 p-1.5 rounded-lg text-gray-400 hover:text-red-500 hover:bg-red-50 transition-all"
                    title="删除">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <polyline points="3 6 5 6 21 6" /><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
                    </svg>
                  </button>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Anime character - bottom right corner */}
      <div className="fixed bottom-4 right-6 z-20 hidden md:block">
        <div className="relative">
          {/* Oval speech bubble */}
          <div className="absolute -top-10 left-1/2 -translate-x-1/2 whitespace-nowrap bg-white/80 backdrop-blur-sm border border-violet-200/50 shadow-sm"
               style={{ borderRadius: '999px', padding: '6px 18px' }}>
            <span className="text-sm font-medium" style={{ fontFamily: '"ZCOOL KuaiLe", cursive', color: '#8b7fc7' }}>
              欢迎来到「月读」的世界^_^
            </span>
          </div>
          {/* Character image - no border, no float */}
          <img src="/maid.png" alt="maid" className="w-44 h-auto" style={{ filter: 'drop-shadow(0 4px 12px rgba(0,0,0,0.08))' }} />
        </div>
      </div>
    </div>
  );
}

/* ═══════════════════════════════════════════ */
/*  Markdown / Table renderers                */
/* ═══════════════════════════════════════════ */

function cleanLatexMath(latex: string): string {
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

function renderMathInHtml(rawHtml: string): string {
  if (!rawHtml) return '';
  // 1. Display math $$...$$
  let res = rawHtml.replace(/\$\$([\s\S]+?)\$\$/g, (_, math) => {
    try {
      const clean = cleanLatexMath(math.trim());
      return `<div class="katex-display my-1 overflow-x-auto">${katex.renderToString(clean, { displayMode: true, throwOnError: false })}</div>`;
    } catch {
      return `$$${math}$$`;
    }
  });
  // 2. Inline math $...$
  res = res.replace(/\$([^\$\n]+?)\$/g, (_, math) => {
    try {
      const clean = cleanLatexMath(math.trim());
      return katex.renderToString(clean, { displayMode: false, throwOnError: false });
    } catch {
      return `$${math}$`;
    }
  });
  return res;
}


function TableBlock({ html }: { html: string }) {
  const processed = renderMathInHtml(html);
  return (
    <div className="text-xs [&_table]:w-full [&_table]:border-collapse [&_table]:rounded-xl [&_table]:overflow-hidden
      [&_td]:border [&_td]:border-gray-200/80 [&_td]:px-3 [&_td]:py-2
      [&_th]:border [&_th]:border-gray-200/80 [&_th]:px-3 [&_th]:py-2
      [&_th]:bg-violet-50/70 [&_th]:font-semibold [&_th]:text-violet-900
      [&_td]:bg-white [&_tr:nth-child(even)_td]:bg-gray-50/40 [&_tr:hover_td]:bg-violet-50/40 text-gray-700
      overflow-x-auto shadow-xs"
      dangerouslySetInnerHTML={{ __html: processed }} />
  );
}

const IMG_BASE = 'http://localhost:7860';

/* ═══════════════════════════════════════════ */
/*  Preview                                   */
/* ═══════════════════════════════════════════ */
const BlockItem = memo(({
  b,
  taskId,
  refIndex,
  onJumpToReference,
  onOpenVariableInspector,
  prevBlock,
  nextBlock,
}: {
  b: BlockData;
  taskId: string;
  refIndex: Record<string, ReferenceItem>;
  onJumpToReference: (id: string, page?: number) => void;
  onOpenVariableInspector?: () => void;
  prevBlock?: BlockData;
  nextBlock?: BlockData;
}) => {
  if (b.type === 'equation') {
    return (
      <EquationCard
        text={b.en}
        page={b.page}
        idx={b.idx}
        contextEn={`${prevBlock?.en || ''} ${nextBlock?.en || ''}`}
        contextZh={`${prevBlock?.zh || ''} ${nextBlock?.zh || ''}`}
        onOpenVariableInspector={onOpenVariableInspector}
      />
    );
  }
  if (b.type === 'table') {
    return (
      <div className="block-card mx-2 my-2 px-4 py-3 rounded-xl overflow-x-auto">
        <div className="flex items-center gap-1.5 mb-2">
          <span className="text-[10px] font-semibold uppercase tracking-wider text-emerald-600 bg-emerald-50 px-2 py-0.5 rounded">Table</span>
        </div>
        <TableBlock html={b.en} />
      </div>
    );
  }
  if (b.type === 'image' || b.type === 'chart' || b.type === 'figure') {
    return (
      <div className="mx-2 my-3 text-center">
        {b.figure_id
          ? <img src={`${IMG_BASE}/api/image/${taskId}/${b.figure_id}`}
               className="max-w-full rounded-xl border border-gray-100 mx-auto shadow-sm" alt={b.type} />
          : <div className="py-10 text-gray-300 text-sm italic">({b.type})</div>}
      </div>
    );
  }
  if (b.type === 'image_caption') {
    return (
      <div className="mx-2 my-1.5 text-center text-sm">
        <InteractiveText text={b.en} refIndex={refIndex} onJumpToReference={onJumpToReference} />
        {b.zh && b.zh !== b.en && (
          <div className="text-gray-600 mt-1">
            <StreamReveal textLen={b.zh.length}>
              <InteractiveText text={b.zh} refIndex={refIndex} onJumpToReference={onJumpToReference} />
            </StreamReveal>
          </div>
        )}
      </div>
    );
  }
  if (b.type === 'page_number') return null;

  // Extract reference number if this block is in references section
  const refNumMatch = b.en.match(/^\s*(?:\[\s*(\d+)\s*\]|(\d+)\.\s+)/);
  const refNum = refNumMatch ? (refNumMatch[1] || refNumMatch[2]) : undefined;
  const refAnchorId = refNum ? `ref-item-${refNum}` : undefined;
  const isRefBlock = b.type === 'ref_text' || !!refAnchorId;
  const isPrimaryTitle = b.type === 'title' && b.page === 1;

  return (
    <div
      id={refAnchorId}
      className={`block-card mx-2 my-1.5 px-4 py-3 rounded-xl overflow-hidden transition-all duration-300 scroll-mt-36
        ${isPrimaryTitle ? 'text-center py-5 my-2.5 bg-white/95 shadow-sm border border-violet-100/70' : ''}
        ${b.type === 'ref_text' ? 'bg-gray-50/70 border-gray-100/90' : ''}
        ${b.verified === false ? 'ring-1 ring-red-200 bg-red-50/30' : ''}`}
    >
      {b.type !== 'text' && !isPrimaryTitle && (
        <div className="flex items-center gap-1.5 mb-2">
          <span className="inline-block text-[10px] font-semibold uppercase tracking-wider text-violet-500 bg-violet-50 px-2 py-0.5 rounded">
            {b.type === 'ref_text' ? 'Reference' : b.type}
          </span>
          {refNum && (
            <span className="font-mono text-[10px] font-bold text-violet-700 bg-violet-100/80 px-1.5 py-0.2 rounded">
              [{refNum}]
            </span>
          )}
        </div>
      )}

      {b.zh === b.en ? (
        /* Passthrough: 只显示一次，原文样式 */
        <div className={`${isPrimaryTitle ? 'text-xl sm:text-2xl font-bold tracking-tight text-gray-900 leading-snug' : b.type === 'title' ? 'text-lg font-semibold text-gray-800' : 'text-sm text-gray-700'} leading-relaxed break-words overflow-hidden`}>
          <InteractiveText text={b.en} refIndex={refIndex} onJumpToReference={onJumpToReference} isRefBlock={isRefBlock} />
        </div>
      ) : (
        <>
          {/* English */}
          <div className={`${isPrimaryTitle ? 'text-xl sm:text-2xl font-bold tracking-tight text-gray-900 leading-snug pb-1' : b.type === 'title' ? 'text-lg font-semibold text-gray-600 pb-1' : 'text-sm text-gray-400 pb-2 italic'} leading-relaxed break-words overflow-hidden`}>
            <InteractiveText text={b.en} refIndex={refIndex} onJumpToReference={onJumpToReference} isRefBlock={isRefBlock} />
          </div>

          {/* Separator */}
          <div className={`h-px bg-gradient-to-r from-violet-100 via-violet-50 to-transparent my-1 ${isPrimaryTitle ? 'w-2/3 mx-auto from-transparent via-violet-200 to-transparent my-2' : ''}`} />

          {/* Chinese — CSS 揭示动画，保留 KaTeX 渲染 */}
          <div className={`${isPrimaryTitle ? 'text-lg sm:text-xl font-semibold text-violet-950 leading-snug' : b.type === 'title' ? 'text-lg font-semibold text-gray-800' : 'text-[15px] text-gray-800'} leading-relaxed break-words overflow-hidden`}>
            {b.zh ? (
              <StreamReveal textLen={b.zh.length}>
                <InteractiveText text={b.zh} refIndex={refIndex} onJumpToReference={onJumpToReference} isRefBlock={isRefBlock} />
              </StreamReveal>
            ) : (
              <span className="text-violet-400/80 italic animate-pulse-soft text-xs inline-flex items-center gap-1.5 py-0.5">
                <span className="inline-block w-1.5 h-1.5 rounded-full bg-violet-400 animate-ping" />
                等待翻译...
              </span>
            )}
          </div>
        </>
      )}

      {b.verified === false && (
        <div className="flex items-center gap-1 mt-2 text-xs text-red-400">
          <IconAlert /> 回译验证未通过
        </div>
      )}
    </div>
  );
});

/* ════════════════════════════════════════════════════════════════
   Generalized Academic Header & Author Showcase System
   ════════════════════════════════════════════════════════════════ */

interface ParsedAuthor {
  name: string;
  markers: string[];
}

interface ParsedAuthorMetadata {
  authors: ParsedAuthor[];
  affiliations: string[];
  emails: string[];
  urls: string[];
  notes: string[];
  unclassified: string[];
  zhAffiliations: string[];
  zhNotes: string[];
}

const AFFILIATION_REGEX = /\b(university|college|institute|institution|department|dept\.?|laboratory|laboratories|labs?|school|center|centre|academy|faculty|corporation|inc\.?|corp\.?|llc|ltd\.?|technologies|hospital|research|google|microsoft|meta|apple|amazon|openai|deepmind|baidu|tencent|alibaba|huawei|bytedance|tsinghua|peking|stanford|mit|berkeley|cmu|harvard|oxford|cambridge|toronto|carnegie|division|telecom)\b/i;
const NOTE_REGEX = /\b(equal contribution|correspondence|corresponding author|work performed|listing order|all authors contributed|supported by|grant|project funded|technical report)\b/i;
const EMAIL_REGEX = /(?:\{[^}]+\}|[a-zA-Z0-9._%+-]+)@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}/g;
const URL_REGEX = /https?:\/\/[^\s)]+/g;

function parseAuthorCandidateBlocks(blocks: BlockData[], allBlocks?: BlockData[]): ParsedAuthorMetadata {
  const authors: ParsedAuthor[] = [];
  const affiliations: string[] = [];
  const emails: string[] = [];
  const urls: string[] = [];
  const notes: string[] = [];
  const unclassified: string[] = [];
  const zhAffiliations: string[] = [];
  const zhNotes: string[] = [];

  const seenEmails = new Set<string>();
  const seenAffiliations = new Set<string>();
  const seenAuthors = new Set<string>();
  const seenUrls = new Set<string>();

  // 0. Extract repository links and footnotes from page 1
  if (allBlocks) {
    const p1Blocks = allBlocks.filter(b => b.page === 1);
    for (const b of p1Blocks) {
      const fixed = (b.en || '').replace(/(https?:\/\/[a-zA-Z0-9_.-]+)\s*\.\s*([a-zA-Z]{2,}[^\s)]*)/g, '$1.$2');
      const mUrls = fixed.match(URL_REGEX);
      if (mUrls) {
        mUrls.forEach(u => {
          const cleanU = u.replace(/[.,;)]+$/, '');
          if (!seenUrls.has(cleanU) && /(?:github\.com|huggingface\.co|arxiv\.org|gitlab\.com|https?:\/\/)/i.test(cleanU)) {
            seenUrls.add(cleanU);
            urls.push(cleanU);
          }
        });
      }
      const enTrim = (b.en || '').trim();
      if (NOTE_REGEX.test(enTrim) && enTrim.length < 200 && !notes.includes(enTrim)) {
        notes.push(enTrim);
        if (b.zh && b.zh !== b.en && !b.zh.startsWith('[ERROR') && !zhNotes.includes(b.zh)) {
          zhNotes.push(b.zh);
        }
      }
    }
  }

  function addAuthor(item: string) {
    let name = item.trim();
    if (!name) return;
    const markers: string[] = [];

    function repMath(content: string) {
      const tokens = content.match(/[0-9]+|\*|†|‡|§|\\dagger|\\ddagger/g);
      if (tokens) {
        tokens.forEach(t => {
          let cleanT = t.replace(/\\/g, '').trim();
          if (cleanT === 'dagger') cleanT = '†';
          else if (cleanT === 'ddagger') cleanT = '‡';
          if (cleanT) markers.push(cleanT);
        });
      }
      return '';
    }

    name = name
      .replace(/\$\^?\{([^}]+)\}\$/g, (_, c) => repMath(c))
      .replace(/\$([0-9a-zA-Z*†‡§,\s\\]+)\$/g, (_, c) => repMath(c))
      .replace(/[\s,]*([*†‡§0-9]+|\([0-9*†‡§,]+\)|\[[0-9*†‡§,]+\])[\s,]*$/g, (_, p1) => {
        const found = p1.match(/[*†‡§0-9]+/g);
        if (found) found.forEach((x: string) => markers.push(x));
        return '';
      })
      .replace(/[*†‡§]+$/g, (m) => {
        markers.push(m);
        return '';
      }).trim();

    if (name && name.length >= 2 && name.length <= 50 && /[a-zA-Z\u00C0-\u024F\u4e00-\u9fa5]/.test(name)) {
      const key = name.toLowerCase();
      if (!seenAuthors.has(key)) {
        seenAuthors.add(key);
        authors.push({ name, markers: [...new Set(markers)] });
      }
    } else if (item.length > 0 && !/^[\s*†‡§0-9]+$/.test(item)) {
      unclassified.push(item);
    }
  }

  function addAffiliation(aff: string, zh?: string) {
    const clean = aff.replace(/^[0-9*†‡§,\s]+|[,\s]+$/g, '').trim();
    if (clean && !seenAffiliations.has(clean.toLowerCase())) {
      seenAffiliations.add(clean.toLowerCase());
      affiliations.push(clean);
      if (zh && zh !== aff && !zh.startsWith('[ERROR')) {
        const cleanZh = zh.replace(/^[0-9*†‡§,\s]+|[,\s]+$/g, '').trim();
        if (cleanZh && !zhAffiliations.includes(cleanZh)) {
          zhAffiliations.push(cleanZh);
        }
      }
    }
  }

  for (const b of blocks) {
    let rawText = b.en || '';
    if (b.type === 'table') {
      rawText = rawText.replace(/<\/td>/gi, '\n').replace(/<\/tr>/gi, '\n').replace(/<[^>]+>/g, ' ');
    }
    // Fix broken OCR spaces in URLs like github. com
    rawText = rawText.replace(/(https?:\/\/[a-zA-Z0-9_.-]+)\s*\.\s*([a-zA-Z]{2,}[^\s)]*)/g, '$1.$2');
    const lines = rawText.split(/[\r\n]+/).map(s => s.trim()).filter(Boolean);

    for (let line of lines) {
      // 1. Extract URLs
      const matchedUrls = line.match(URL_REGEX);
      if (matchedUrls) {
        matchedUrls.forEach(u => {
          const cleanU = u.replace(/[.,;)]+$/, '');
          if (!seenUrls.has(cleanU)) {
            seenUrls.add(cleanU);
            urls.push(cleanU);
          }
        });
        line = line.replace(URL_REGEX, '').trim();
      }

      // 2. Extract emails
      const matchedEmails = line.match(EMAIL_REGEX);
      if (matchedEmails) {
        matchedEmails.forEach(em => {
          const cleanEmail = em.replace(/\s+/g, '');
          if (!seenEmails.has(cleanEmail)) {
            seenEmails.add(cleanEmail);
            emails.push(cleanEmail);
          }
        });
        line = line.replace(EMAIL_REGEX, '').trim();
      }

      if (!line) continue;

      // 3. Notes / footnotes
      if (NOTE_REGEX.test(line) || ((line.startsWith('*') || line.startsWith('†')) && line.length > 25)) {
        if (!notes.includes(line)) {
          notes.push(line);
          if (b.zh && b.zh !== b.en && !b.zh.startsWith('[ERROR') && !zhNotes.includes(b.zh)) {
            zhNotes.push(b.zh);
          }
        }
        continue;
      }

      // 4. Check if line is pure affiliation or contains multiple universities/institutions
      const hasAffil = AFFILIATION_REGEX.test(line);
      const isPureAffil =
        /^\s*(?:\$\^?\{[0-9*†‡,]+\}\$|\^[0-9*†‡,]+|[0-9*†‡§]+\s+)/.test(line) && hasAffil;

      if (isPureAffil || (hasAffil && (line.match(AFFILIATION_REGEX) || []).length >= 2)) {
        const parts = line.split(/(?:\$\^?\{[0-9*†‡,]+\}\$|\^[0-9*†‡,]+|[;]+|\s{2,})/);
        for (const part of parts) {
          const p = part.replace(/^[0-9*†‡§,\s]+|[,\s]+$/g, '').trim();
          if (p && p.length > 3 && !seenAffiliations.has(p.toLowerCase()) && AFFILIATION_REGEX.test(p)) {
            addAffiliation(p, b.zh);
          }
        }
        continue;
      }

      if (hasAffil) {
        const affMatch = line.match(AFFILIATION_REGEX);
        if (affMatch && affMatch.index !== undefined && affMatch.index > 3 && !line.slice(0, affMatch.index).includes(',')) {
          const potentialAuthor = line.slice(0, affMatch.index).trim();
          const potentialAff = line.slice(affMatch.index).trim();
          addAuthor(potentialAuthor);
          addAffiliation(potentialAff, b.zh);
          continue;
        } else {
          addAffiliation(line, b.zh);
          continue;
        }
      }

      // 5. Split authors by comma (not inside braces)
      const parts = line.split(/,\s*(?![^{}]*\})|\s+and\s+/);
      for (const part of parts) {
        addAuthor(part);
      }
    }
  }

  return { authors, affiliations, emails, urls, notes, unclassified, zhAffiliations, zhNotes };
}

const AuthorMetadataCard = memo(({
  blocks,
  allBlocks,
}: {
  blocks: BlockData[];
  allBlocks?: BlockData[];
}) => {
  const [showRaw, setShowRaw] = useState(false);
  const metadata = useMemo(() => parseAuthorCandidateBlocks(blocks, allBlocks), [blocks, allBlocks]);

  return (
    <div className="liquid-glass-card mx-2 my-3 p-5 sm:p-6 rounded-2xl border border-white/60 shadow-sm text-center relative overflow-hidden transition-all duration-300">
      {/* Top Header Tag */}
      <div className="flex items-center justify-between mb-3.5 px-1">
        <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[11px] font-medium tracking-wide text-violet-700 bg-violet-50/90 border border-violet-100/80 select-none">
          <span className="w-1.5 h-1.5 rounded-full bg-violet-500" />
          Authors & Affiliations
        </span>
        <button
          type="button"
          onClick={() => setShowRaw(!showRaw)}
          className="text-[11px] text-gray-400 hover:text-violet-600 transition-colors select-none font-medium px-2 py-0.5 rounded hover:bg-white/60"
        >
          {showRaw ? '精简视图' : '查看原始行'}
        </button>
      </div>

      {showRaw ? (
        <div className="text-left space-y-1.5 py-1 px-2 font-mono text-xs text-gray-600 bg-gray-50/60 rounded-xl p-3 border border-gray-100">
          {blocks.map((b, i) => (
            <div key={i} className="leading-relaxed border-b border-gray-100/60 last:border-b-0 pb-1">
              <span className="text-[10px] text-violet-500 font-semibold mr-2">[{b.idx}]</span>
              <span>{b.en}</span>
            </div>
          ))}
        </div>
      ) : (
        <>
          {/* Authors List */}
          {metadata.authors.length > 0 && (
            <div className="flex flex-wrap items-center justify-center gap-x-3.5 gap-y-1.5 text-center">
              {metadata.authors.map((author, i) => (
                <span
                  key={i}
                  className="inline-flex items-center text-[15px] sm:text-base font-medium text-gray-800 hover:text-violet-700 transition-colors cursor-default"
                >
                  <span>{author.name}</span>
                  {author.markers.length > 0 && (
                    <sup className="text-violet-600 font-semibold text-[10px] ml-0.5 tracking-tighter select-none">
                      {author.markers.join(' ')}
                    </sup>
                  )}
                  {i < metadata.authors.length - 1 && (
                    <span className="text-gray-300 ml-3.5 select-none font-light">•</span>
                  )}
                </span>
              ))}
            </div>
          )}

          {/* Affiliations */}
          {metadata.affiliations.length > 0 && (
            <div className="flex flex-wrap items-center justify-center gap-x-3.5 gap-y-1 mt-3 text-xs sm:text-[13px] text-gray-500 text-center leading-relaxed">
              {metadata.affiliations.map((aff, i) => (
                <span key={i} className="inline-flex items-center">
                  <span>{aff}</span>
                  {i < metadata.affiliations.length - 1 && (
                    <span className="text-gray-300 ml-3.5 select-none">•</span>
                  )}
                </span>
              ))}
            </div>
          )}

          {/* Translated Affiliations (if any) */}
          {metadata.zhAffiliations.length > 0 && (
            <div className="flex flex-wrap items-center justify-center gap-x-3.5 gap-y-1 mt-1 text-xs text-gray-400 text-center leading-relaxed">
              {metadata.zhAffiliations.map((aff, i) => (
                <span key={i} className="inline-flex items-center">
                  <span>{aff}</span>
                  {i < metadata.zhAffiliations.length - 1 && (
                    <span className="text-gray-300 ml-3.5 select-none">•</span>
                  )}
                </span>
              ))}
            </div>
          )}

          {/* URLs & Repository links */}
          {metadata.urls.length > 0 && (
            <div className="flex flex-wrap items-center justify-center gap-2 mt-3 pt-2">
              {metadata.urls.map((url, i) => (
                <a
                  key={i}
                  href={url}
                  target="_blank"
                  rel="noreferrer"
                  className="font-mono text-[11px] text-violet-600 hover:text-violet-800 bg-violet-50/70 hover:bg-violet-100/70 px-2.5 py-0.5 rounded-full border border-violet-100 transition-all flex items-center gap-1"
                >
                  <span className="underline">{url.replace(/^https?:\/\//, '')}</span>
                </a>
              ))}
            </div>
          )}

          {/* Emails */}
          {metadata.emails.length > 0 && (
            <div className="flex flex-wrap items-center justify-center gap-1.5 mt-3.5 pt-3 border-t border-gray-100/80">
              {metadata.emails.map((email, i) => (
                <a
                  key={i}
                  href={`mailto:${email.replace(/^\{[^}]+\}/, '')}`}
                  title={`Send email to ${email}`}
                  className="font-mono text-[11px] text-gray-500 hover:text-violet-600 bg-white/70 hover:bg-violet-50/80 px-2.5 py-0.5 rounded-full border border-gray-100/90 transition-all select-all shadow-2xs"
                >
                  {email}
                </a>
              ))}
            </div>
          )}

          {/* Footnotes / Notes */}
          {(metadata.notes.length > 0 || metadata.zhNotes.length > 0) && (
            <div className="mt-3.5 pt-2.5 text-[11px] text-gray-400 italic text-center space-y-0.5 border-t border-gray-100/60 leading-relaxed">
              {metadata.notes.map((note, i) => (
                <div key={i}>{note}</div>
              ))}
              {metadata.zhNotes.map((note, i) => (
                <div key={`zh-${i}`} className="text-gray-500">{note}</div>
              ))}
            </div>
          )}

          {/* Unclassified Fallback if no authors recognized */}
          {metadata.authors.length === 0 && metadata.unclassified.length > 0 && (
            <div className="space-y-1 text-sm text-gray-600 py-1">
              {metadata.unclassified.map((line, i) => (
                <div key={i}>{line}</div>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
});

type RenderItem =
  | { kind: 'block'; block: BlockData; origIdx: number; animIdx: number; pageBreak: boolean }
  | { kind: 'author_group'; blocks: BlockData[]; allBlocks?: BlockData[]; animIdx: number; pageBreak: boolean }
  | {
      kind: 'code_group';
      blocks: BlockData[];
      code: string;
      caption?: string;
      captionZh?: string;
      page: number;
      idx: number;
      animIdx: number;
      pageBreak: boolean;
    };

function groupBlocksForRendering(blocks: BlockData[]): RenderItem[] {
  const items: RenderItem[] = [];
  let lastPage = 0;

  // Find page 1 primary title
  const firstTitleIdx = blocks.findIndex(b => b.page === 1 && b.type === 'title');

  // Find range of consecutive titles on page 1 (e.g. main title + subtitle)
  let lastTitleIdx = -1;
  if (firstTitleIdx !== -1) {
    lastTitleIdx = firstTitleIdx;
    while (
      lastTitleIdx + 1 < blocks.length &&
      blocks[lastTitleIdx + 1].page === 1 &&
      blocks[lastTitleIdx + 1].type === 'title'
    ) {
      const nextEn = (blocks[lastTitleIdx + 1].en || '').trim().toLowerCase();
      if (nextEn.startsWith('abstract') || nextEn.startsWith('摘要')) break;
      lastTitleIdx++;
    }
  }

  // Check candidate author blocks between lastTitleIdx and abstract/section start
  let authorEndIdx = -1;
  const candidateBlocks: BlockData[] = [];

  if (lastTitleIdx !== -1) {
    for (let i = lastTitleIdx + 1; i < blocks.length; i++) {
      const b = blocks[i];
      if (b.page !== 1) break;

      const enLower = (b.en || '').trim().toLowerCase();

      // Check if table is actually an author grid (contains @ or affiliation)
      const isTableAuthorGrid =
        b.type === 'table' && (EMAIL_REGEX.test(b.en || '') || AFFILIATION_REGEX.test(b.en || ''));

      if (isTableAuthorGrid) {
        candidateBlocks.push(b);
        continue;
      }

      const isAuthorOrAffil =
        (b.en || '').split(',').length >= 3 ||
        /\$\^?\{?[*†‡0-9a-z,\s]+\}?\s*\$/i.test(b.en || '') ||
        AFFILIATION_REGEX.test(b.en || '') ||
        EMAIL_REGEX.test(b.en || '') ||
        NOTE_REGEX.test(enLower) ||
        /\b(?:correspondence|equal contribution|university|institute|laboratory|department|school)\b/i.test(enLower);

      const isStop =
        b.type === 'header' ||
        (b.type === 'title' && !enLower.startsWith('author')) ||
        enLower.startsWith('abstract') ||
        enLower.startsWith('摘要') ||
        /^(?:(?:\d+\.?|[I|V|X]+\.?)\s+)?(?:introduction|overview)/i.test(enLower) ||
        ['equation', 'table', 'image', 'chart', 'figure'].includes(b.type) ||
        (!isAuthorOrAffil && (b.en || '').length > 280);

      if (isStop) {
        authorEndIdx = i;
        break;
      }

      // Skip arXiv header aside_text
      if (b.type === 'aside_text' && enLower.includes('arxiv')) {
        continue;
      }

      candidateBlocks.push(b);
    }
  }

  const shouldGroupAuthors =
    candidateBlocks.length > 0 &&
    (candidateBlocks.length >= 2 ||
      EMAIL_REGEX.test(candidateBlocks[0].en || '') ||
      AFFILIATION_REGEX.test(candidateBlocks[0].en || '') ||
      (candidateBlocks[0].en || '').includes('*') ||
      (candidateBlocks[0].en || '').includes('$'));

  let animCounter = 0;
  for (let i = 0; i < blocks.length; i++) {
    const b = blocks[i];
    const pageBreak = b.page !== lastPage;
    lastPage = b.page;

    if (shouldGroupAuthors && i === lastTitleIdx + 1) {
      items.push({
        kind: 'author_group',
        blocks: candidateBlocks,
        allBlocks: blocks,
        animIdx: animCounter++,
        pageBreak: false,
      });
      i = (authorEndIdx !== -1 ? authorEndIdx : lastTitleIdx + candidateBlocks.length) - 1;
      continue;
    }

    // Check for code / pseudocode / algorithm sequence or preceding caption
    const isCap = isCodeCaption(b.en);
    const nextIsCode =
      i + 1 < blocks.length &&
      blocks[i + 1].page === b.page &&
      (isCodeBlock(blocks[i + 1].en) || blocks[i + 1].type === 'algorithm');
    const isCode = isCodeBlock(b.en) || b.type === 'algorithm';

    if (isCode || (isCap && nextIsCode)) {
      let j = i;
      const cluster: BlockData[] = [];

      while (j < blocks.length && blocks[j].page === b.page) {
        const cur = blocks[j];
        const curIsCode = isCodeBlock(cur.en) || cur.type === 'algorithm';
        const curIsCap = isCodeCaption(cur.en);
        const hasCodeOrCapAhead = blocks
          .slice(j + 1)
          .some(x => x.page === b.page && (isCodeBlock(x.en) || x.type === 'algorithm' || isCodeCaption(x.en)));
        const curIsComment = !isSectionHeading(cur.en) && cur.en.length < 100 && hasCodeOrCapAhead;

        if (curIsCode || curIsCap || curIsComment) {
          cluster.push(cur);
          j++;
        } else {
          break;
        }
      }

      const codeAndComments = cluster.filter(cb => !isCodeCaption(cb.en));
      const captionBlocks = cluster.filter(cb => isCodeCaption(cb.en));

      if (codeAndComments.length > 0) {
        const snippets: BlockData[][] = [];
        let curSnippet: BlockData[] = [];

        for (const item of codeAndComments) {
          if (curSnippet.length > 0 && isCodeStart(item.en)) {
            snippets.push(curSnippet);
            curSnippet = [item];
          } else {
            curSnippet.push(item);
          }
        }
        if (curSnippet.length > 0) snippets.push(curSnippet);

        snippets.forEach((sn, snIdx) => {
          const fullCode = sn
            .map(item => {
              if (!isCodeBlock(item.en) && item.type !== 'algorithm' && !item.en.trim().startsWith('#')) {
                return '# ' + item.en.trim();
              }
              return item.en;
            })
            .join('\n');

          const matchedCap = matchCodeCaption(fullCode, captionBlocks, snIdx);

          items.push({
            kind: 'code_group',
            blocks: sn,
            code: fullCode,
            caption: matchedCap?.en,
            captionZh: matchedCap?.zh,
            page: sn[0].page,
            idx: sn[0].idx,
            animIdx: animCounter++,
            pageBreak: sn[0].page !== lastPage,
          });
          lastPage = sn[0].page;
        });

        i = j - 1;
        continue;
      }
    }

    items.push({
      kind: 'block',
      block: b,
      origIdx: i,
      animIdx: animCounter++,
      pageBreak,
    });
  }

  return items;
}

const Preview = memo(function Preview({
  blocks,
  taskId,
  phase,
  refIndex,
  onJumpToReference,
  tldr,
  isTLDRLoading,
  onOpenVariableInspector,
}: {
  blocks: BlockData[];
  taskId: string;
  phase?: string;
  refIndex: Record<string, ReferenceItem>;
  onJumpToReference: (id: string, page?: number) => void;
  tldr?: PaperTLDR | null;
  isTLDRLoading?: boolean;
  onOpenVariableInspector?: () => void;
}) {
  const renderItems = useMemo(() => groupBlocksForRendering(blocks), [blocks]);
  const hasAuthorGroup = useMemo(() => renderItems.some(it => it.kind === 'author_group'), [renderItems]);

  if (blocks.length === 0) {
    return (
      <div className="text-center py-16 animate-fade-in">
        <img src="/maid.png" alt="loading" className="w-32 h-auto mx-auto mb-4 opacity-60 animate-float" />
        <p className="text-gray-400 text-sm">
          {phase === 'ocr' ? '正在识别页面内容，请稍等~' : '正在努力翻译中，稍等一下~'}
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-1">
      {renderItems.map((item, index) => {
        if (item.kind === 'author_group') {
          return (
            <React.Fragment key="page-1-author-and-tldr">
              <div
                className={`animate-slide-in ${index > 5 ? 'deferred-block' : ''}`}
                style={{ animationDelay: `${Math.min(item.animIdx * 0.03, 0.5)}s` }}
              >
                <AuthorMetadataCard blocks={item.blocks} allBlocks={item.allBlocks} />
              </div>
              <PaperTLDRCard tldr={tldr || undefined} loading={isTLDRLoading} />
            </React.Fragment>
          );
        }

        if (item.kind === 'code_group') {
          return (
            <div
              key={`code-group-p${item.page}-i${item.idx}`}
              className={`animate-slide-in ${index > 5 ? 'deferred-block' : ''}`}
              style={{ animationDelay: `${Math.min(item.animIdx * 0.03, 0.5)}s` }}
            >
              {item.pageBreak && (
                <div data-page={item.page} className="flex items-center gap-3 mt-8 mb-4 scroll-mt-36">
                  <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-white/60 backdrop-blur-sm border border-white/40 shadow-sm">
                    <IconPage /><span className="text-sm font-semibold text-violet-600">第 {item.page} 页</span>
                  </div>
                  <div className="flex-1 h-px bg-gradient-to-r from-violet-200/60 via-violet-100/30 to-transparent" />
                </div>
              )}
              <CodeCard
                code={item.code}
                caption={item.caption}
                captionZh={item.captionZh}
                page={item.page}
                idx={item.idx}
              />
            </div>
          );
        }

        const b = item.block;
        const isFirstPageTitle = b.page === 1 && b.type === 'title';
        const nextItem = index < renderItems.length - 1 ? renderItems[index + 1] : null;
        const showTLDRAfterTitle = !hasAuthorGroup && isFirstPageTitle && (
          !nextItem || nextItem.kind !== 'block' || nextItem.block.type !== 'title'
        );

        return (
          <React.Fragment key={`${b.page}-${b.idx}`}>
            <div
              className={`animate-slide-in ${index > 5 ? 'deferred-block' : ''}`}
              style={{ animationDelay: `${Math.min(item.animIdx * 0.03, 0.5)}s` }}
            >
              {item.pageBreak && (
                <div data-page={b.page} className="flex items-center gap-3 mt-8 mb-4 scroll-mt-36">
                  <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-white/60 backdrop-blur-sm border border-white/40 shadow-sm">
                    <IconPage /><span className="text-sm font-semibold text-violet-600">第 {b.page} 页</span>
                  </div>
                  <div className="flex-1 h-px bg-gradient-to-r from-violet-200/60 via-violet-100/30 to-transparent" />
                </div>
              )}
              <BlockItem
                b={b}
                taskId={taskId}
                refIndex={refIndex}
                onJumpToReference={onJumpToReference}
                onOpenVariableInspector={onOpenVariableInspector}
                prevBlock={item.origIdx > 0 ? blocks[item.origIdx - 1] : undefined}
                nextBlock={item.origIdx < blocks.length - 1 ? blocks[item.origIdx + 1] : undefined}
              />
            </div>
            {showTLDRAfterTitle && (
              <PaperTLDRCard tldr={tldr || undefined} loading={isTLDRLoading} />
            )}
          </React.Fragment>
        );
      })}
    </div>
  );
});

