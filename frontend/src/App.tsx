import { useState, useCallback, useRef, useEffect, memo, type ReactNode } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkMath from 'remark-math';
import rehypeKatex from 'rehype-katex';
import katex from 'katex';
import 'katex/dist/katex.min.css';
import {
  uploadPdf, startTranslation, cancelTranslation, getDownloadUrl,
  listHistory, loadHistoryTask, deleteHistoryTask, getOcrModels,
  type HistoryItem, type OcrModelInfo
} from './api';
import { useWebSocket } from './hooks/useWebSocket';

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
  const blocksRef = useRef<BlockData[]>([]);
  const mainRef = useRef<HTMLDivElement>(null);

  /* ── 加载历史记录与可用 OCR 模型 ── */
  useEffect(() => {
    listHistory().then(setHistory).catch(() => {});
    getOcrModels().then(models => {
      if (models && models.length > 0) {
        setOcrModels(models);
        const def = models.find(m => m.is_default);
        if (def) setSelectedOcrModel(def.id);
      }
    }).catch(() => {});
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
  };

  const onWsEvent = useCallback((e: Record<string, unknown>) => {
    switch (e.type) {
      case 'start':
        setTotalPages(e.total_pages as number);
        if (e.ocr_model) {
          setTask(prev => prev ? { ...prev, ocr_model: e.ocr_model as string } : prev);
        }
        break;
      case 'phase':
        setPhase(e.phase as 'ocr' | 'translate');
        if (e.total_blocks) setTransTotal(e.total_blocks as number);
        break;
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
        const q = (e.quality as { total_blocks: number; pass_rate: string }) || null;
        setTask(prev => prev ? {
          ...prev,
          status: 'completed',
          quality: q || { total_blocks: blocksRef.current.length, pass_rate: '100%' }
        } : prev);
        break;
      }
      case 'error': setError(e.message as string); break;
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

  const scrollToPage = (page: number) => {
    setActivePage(page);
    const el = mainRef.current?.querySelector(`[data-page="${page}"]`);
    el?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  };

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
      <header className="sticky top-0 z-50 border-b border-white/30 bg-white/40 backdrop-blur-[50px] saturate-[1.8] shadow-[inset_0_1px_0_rgba(255,255,255,0.5)]">
        <div className="max-w-[95rem] mx-auto px-6 py-1 flex items-end justify-between">
          <div className="flex items-end gap-2.5">
            <img src="/logo.jpg" alt="logo" className="w-20 h-20 rounded-full object-cover border-2 border-white/60 shadow-sm -mb-8" />
            <span className="font-semibold text-gray-900 tracking-tight mb-1">LunePaper</span>
          </div>

          <div className="flex items-center gap-3">
            {task && mode !== 'upload' && (
              <>
                <span className="text-gray-400 flex items-center gap-1.5 text-sm"><IconFile />{task.filename}</span>
                <span className="text-gray-300">·</span>
                <span className="text-gray-400 text-sm">{task.page_count} 页</span>
                {task.ocr_model && (
                  <>
                    <span className="text-gray-300">·</span>
                    <span className="text-violet-600 font-medium text-xs bg-violet-50/80 border border-violet-200/50 px-2 py-0.5 rounded-full">
                      {task.ocr_model === 'ovis' ? 'OvisOCR2' : 'Unlimited-OCR'}
                    </span>
                  </>
                )}
                {mode === 'done' && (
                  <span className="inline-flex items-center gap-1 text-emerald-600 bg-emerald-50 px-2 py-0.5 rounded-full text-xs font-medium">
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
                className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-all
                  ${locked
                    ? 'bg-violet-50 text-violet-600 hover:bg-violet-100'
                    : 'bg-gray-100 text-gray-400 hover:bg-gray-200 hover:text-gray-500'
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
                className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-all
                  ${compareMode
                    ? 'bg-violet-50 text-violet-600 hover:bg-violet-100'
                    : 'bg-gray-100 text-gray-400 hover:bg-gray-200 hover:text-gray-500'
                  }`}
              >
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <rect x="2" y="3" width="20" height="18" rx="2" /><line x1="12" y1="3" x2="12" y2="21" />
                </svg>
                对照
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
            <div className="sticky top-14 z-40 mb-5 glass-card animate-fade-in-up rounded-2xl px-5 py-3.5 backdrop-blur-[35px] bg-white/80 border border-white/60 shadow-[0_4px_20px_rgba(139,127,199,0.12)]">
              <div className="flex items-center justify-between gap-5">
                <div className="flex-1">
                  {phase === 'ocr' ? (
                    /* ── OCR 阶段 ── */
                    <>
                      <div className="flex justify-between text-sm mb-2">
                        <span className="text-gray-500 flex items-center gap-2">
                          <span className="relative flex h-2.5 w-2.5">
                            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-violet-400 opacity-75" />
                            <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-violet-500" />
                          </span>
                          OCR 识别中...
                        </span>
                        <span className="text-gray-400 font-medium tabular-nums">
                          {ocrPage} / {totalPages} 页
                          <span className="ml-2 text-violet-500 font-semibold">
                            {totalPages > 0 ? Math.round((ocrPage / totalPages) * 100) : 0}%
                          </span>
                        </span>
                      </div>
                      <div className="h-2.5 bg-gray-100/60 rounded-full overflow-hidden relative">
                        <div className="h-full rounded-full transition-all duration-500 ease-out progress-stripe relative"
                             style={{ width: `${totalPages > 0 ? (ocrPage / totalPages) * 100 : 0}%`,
                                      background: 'linear-gradient(90deg, #8b7fc7, #a89cc8)' }}>
                          <div className="absolute right-0 top-1/2 -translate-y-1/2 w-3 h-3 bg-white rounded-full shadow-md border-2 border-violet-400" />
                        </div>
                      </div>
                    </>
                  ) : (
                    /* ── 翻译阶段 ── */
                    <>
                      <div className="flex justify-between text-sm mb-2">
                        <span className="text-gray-500 flex items-center gap-2">
                          <span className="relative flex h-2.5 w-2.5">
                            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-violet-400 opacity-75" />
                            <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-violet-500" />
                          </span>
                          翻译中...
                        </span>
                        <span className="text-gray-400 font-medium tabular-nums">
                          {transDone} / {transTotal} 块
                          <span className="ml-2 text-violet-500 font-semibold">
                            {transTotal > 0 ? Math.round((transDone / transTotal) * 100) : 0}%
                          </span>
                        </span>
                      </div>
                      <div className="h-2.5 bg-gray-100/60 rounded-full overflow-hidden relative">
                        <div className="h-full rounded-full transition-all duration-500 ease-out progress-stripe relative"
                             style={{ width: `${transTotal > 0 ? (transDone / transTotal) * 100 : 0}%`,
                                      background: 'linear-gradient(90deg, #8b7fc7, #a89cc8)' }}>
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
                  className="shrink-0 inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-rose-500 hover:text-rose-600 bg-rose-50/80 hover:bg-rose-100 rounded-lg transition-all border border-rose-200/50 shadow-sm hover:shadow active:scale-95"
                  title="取消当前翻译任务并释放 GPU 显存"
                >
                  <IconClose /> 取消任务
                </button>
              </div>
            </div>
          )}

          {/* Done bar with Interactive Page Seeking Slider (Sticky top-14) */}
          {mode === 'done' && (
            <div className="sticky top-14 z-40 mb-5 glass-card animate-fade-in-up rounded-2xl px-5 py-3 backdrop-blur-[35px] bg-white/85 border border-white/60 shadow-[0_4px_20px_rgba(139,127,199,0.12)] flex items-center gap-4">
              <div className="flex-1 flex items-center gap-3 min-w-0">
                <span className="text-xs font-semibold text-violet-700 bg-violet-100/80 border border-violet-200/80 px-2.5 py-1 rounded-full whitespace-nowrap shadow-xs">
                  第 {activePage} / {totalPages || task?.page_count || 1} 页
                </span>
                <input
                  type="range"
                  min={1}
                  max={totalPages || task?.page_count || 1}
                  value={activePage}
                  onChange={(e) => scrollToPage(Number(e.target.value))}
                  className="flex-1 h-2 bg-violet-100 rounded-lg appearance-none cursor-pointer accent-violet-600 hover:accent-violet-700 transition-all"
                  title="滑动快速调节当前阅读页码"
                />
              </div>
              <span className="text-xs text-gray-400 whitespace-nowrap hidden sm:inline">
                {task?.quality?.total_blocks ?? blocks.length} 个内容块
              </span>
              <button onClick={() => window.open(getDownloadUrl(task!.task_id))}
                className="inline-flex items-center gap-1.5 px-4 py-2 text-white rounded-lg text-xs font-medium
                           transition-all hover:shadow-md hover:shadow-violet-200 hover:-translate-y-0.5 active:translate-y-0 shrink-0"
                style={{ background: 'linear-gradient(135deg, #8b7fc7, #a89cc8)' }}>
                <IconDownload /> 下载 HTML
              </button>
              <button onClick={() => { if (locked) { if (!confirm('确定要开始新任务吗？当前翻译内容将丢失。')) return; } clear(); }}
                className="inline-flex items-center gap-1.5 px-3 py-2 text-gray-600 bg-white/70 backdrop-blur-sm border border-gray-200/60 rounded-lg text-xs font-medium hover:bg-white transition-all shadow-xs shrink-0">
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
              <Preview blocks={blocks} taskId={task?.task_id ?? ''} phase={phase} />
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
        <div className="mb-4 bg-white/70 backdrop-blur-md border border-white/50 rounded-2xl p-3 shadow-sm flex flex-col gap-2">
          <div className="flex items-center justify-between px-1">
            <span className="text-xs font-semibold text-gray-600 flex items-center gap-1.5">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="text-violet-500">
                <rect x="2" y="3" width="20" height="14" rx="2" /><line x1="8" y1="21" x2="16" y2="21" /><line x1="12" y1="17" x2="12" y2="21" />
              </svg>
              OCR 底座引擎选择:
            </span>
            <span className="text-[11px] text-gray-400 font-mono">
              {selectedOcrModel === 'ovis' ? 'Qwen-VL · n_ctx 8192 · VRAM ~1.7G' : 'DeepSeek2-OCR · n_ctx 8192 · VRAM ~6.0G'}
            </span>
          </div>

          <div className="grid grid-cols-2 gap-2">
            <button
              type="button"
              disabled={!isUnlimitedAvailable}
              onClick={() => onSelectOcrModel('unlimited')}
              className={`px-3 py-2.5 rounded-xl text-left transition-all border ${
                selectedOcrModel === 'unlimited'
                  ? 'bg-violet-50/90 border-violet-300 ring-2 ring-violet-400/30 shadow-sm'
                  : 'bg-white/50 border-gray-100 hover:bg-white/80 hover:border-violet-100 text-gray-600'
              } ${!isUnlimitedAvailable ? 'opacity-50 cursor-not-allowed' : ''}`}
            >
              <div className="flex items-center justify-between">
                <span className="text-xs font-bold text-gray-800">Unlimited-OCR</span>
                <span className="text-[10px] font-semibold text-violet-600 bg-violet-100/70 px-1.5 py-0.5 rounded">3B MoE</span>
              </div>
              <p className="text-[11px] text-gray-500 mt-0.5 truncate font-mono">
                {isUnlimitedAvailable ? '64×550M · Q8_0 · VRAM ~6.0G' : '未检测到模型文件'}
              </p>
            </button>

            <button
              type="button"
              disabled={!isOvisAvailable}
              onClick={() => onSelectOcrModel('ovis')}
              className={`px-3 py-2.5 rounded-xl text-left transition-all border ${
                selectedOcrModel === 'ovis'
                  ? 'bg-violet-50/90 border-violet-300 ring-2 ring-violet-400/30 shadow-sm'
                  : 'bg-white/50 border-gray-100 hover:bg-white/80 hover:border-violet-100 text-gray-600'
              } ${!isOvisAvailable ? 'opacity-50 cursor-not-allowed' : ''}`}
            >
              <div className="flex items-center justify-between">
                <span className="text-xs font-bold text-gray-800">OvisOCR2</span>
                <span className="text-[10px] font-semibold text-emerald-600 bg-emerald-100/70 px-1.5 py-0.5 rounded">0.8B Dense</span>
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
          className={`upload-zone rounded-2xl p-10 text-center cursor-pointer transition-all
            ${drag ? 'dragging border-violet-400 bg-violet-50/50' : 'border-gray-200 hover:border-violet-300 hover:bg-violet-50/30'}`}
          onClick={() => document.getElementById('fileInput')?.click()}>
          <div className={`mx-auto w-16 h-16 rounded-2xl flex items-center justify-center mb-4 transition-all
            ${drag ? 'bg-violet-100 text-violet-600 scale-110' : 'bg-gray-50 text-gray-300'}`}>
            <IconUpload />
          </div>
          <p className="text-gray-600 text-base font-medium mb-1">{drag ? '松开以上传' : '拖拽 PDF 到此处'}</p>
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
                  className="group flex items-center gap-3 px-4 py-2.5 rounded-xl border border-white/40 bg-white/40 backdrop-blur-sm hover:bg-white/70 hover:border-violet-200 transition-all cursor-pointer"
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
function MdBlock({ text }: { text: string }) {
  return (
    <ReactMarkdown remarkPlugins={[remarkMath]} rehypePlugins={[[rehypeKatex, { throwOnError: false }]]}
      components={{ p: ({ children }) => <span>{children}</span> }}>
      {text}
    </ReactMarkdown>
  );
}

function cleanLatexMath(latex: string): string {
  if (!latex) return '';
  return latex
    .replace(/&amp;/g, '&')
    .replace(/\\_\{n\}\s*u\s*m\b/g, '_{\\mathrm{num}}')
    .replace(/step_\\mathrm\{num\}/g, 'step_{\\mathrm{num}}')
    .replace(/warmup_\\mathrm\{steps\}/g, 'warmup_{\\mathrm{steps}}')
    .replace(/-0\.\s+5/g, '-0.5')
    .replace(/-1\.\s+5/g, '-1.5')
    .replace(/\\\s+where\b/g, '\\\\ \\text{where }')
    .replace(/\.\s*\.\s*\./g, '\\dots');
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

function EquationBlock({ text }: { text: string }) {
  let clean = (text || '').trim();
  if (clean.startsWith('$$') && clean.endsWith('$$')) {
    clean = clean.slice(2, -2).trim();
  } else if (clean.startsWith('\\[') && clean.endsWith('\\]')) {
    clean = clean.slice(2, -2).trim();
  }
  clean = cleanLatexMath(clean);

  try {
    const html = katex.renderToString(clean, {
      displayMode: true,
      throwOnError: false,
    });
    return (
      <div
        className="text-center py-2 overflow-x-auto select-text"
        dangerouslySetInnerHTML={{ __html: html }}
      />
    );
  } catch {
    return <MdBlock text={text.startsWith('$$') ? text : `$$\n${text}\n$$`} />;
  }
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
const BlockItem = memo(({ b, taskId }: { b: BlockData; taskId: string }) => {
  if (b.type === 'equation') {
    return (
      <div className="block-card mx-2 my-1.5 px-4 py-3 rounded-xl bg-gray-50/80 overflow-x-auto">
        <EquationBlock text={b.en} />
      </div>
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
        <MdBlock text={b.en} />
        {b.zh && b.zh !== b.en && (
          <div className="text-gray-600 mt-1">
            <StreamReveal textLen={b.zh.length}><MdBlock text={b.zh} /></StreamReveal>
          </div>
        )}
      </div>
    );
  }
  if (b.type === 'page_number') return null;

  return (
    <div className={`block-card mx-2 my-1.5 px-4 py-3 rounded-xl overflow-hidden
      ${b.verified === false ? 'ring-1 ring-red-200 bg-red-50/30' : ''}`}>

      {b.type !== 'text' && (
        <span className="inline-block text-[10px] font-semibold uppercase tracking-wider text-violet-500 bg-violet-50 px-2 py-0.5 rounded mb-2">
          {b.type}
        </span>
      )}

      {b.zh === b.en ? (
        /* Passthrough: 只显示一次，原文样式 */
        <div className={`${b.type === 'title' ? 'text-lg font-semibold' : 'text-sm'} text-gray-700 leading-relaxed break-words overflow-hidden`}>
          <MdBlock text={b.en} />
        </div>
      ) : (
        <>
          {/* English */}
          <div className={`${b.type === 'title' ? 'text-lg font-semibold' : 'text-sm'} ${b.type === 'title' ? 'text-gray-600' : 'text-gray-400'} leading-relaxed pb-2 italic break-words overflow-hidden`}>
            <MdBlock text={b.en} />
          </div>

          {/* Separator */}
          <div className="h-px bg-gradient-to-r from-violet-100 via-violet-50 to-transparent my-1" />

          {/* Chinese — CSS 揭示动画，保留 KaTeX 渲染 */}
          <div className={`${b.type === 'title' ? 'text-lg font-semibold' : 'text-[15px]'} text-gray-800 leading-relaxed break-words overflow-hidden`}>
            {b.zh ? (
              <StreamReveal textLen={b.zh.length}><MdBlock text={b.zh} /></StreamReveal>
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

function Preview({ blocks, taskId, phase }: { blocks: BlockData[]; taskId: string; phase?: string }) {
  let lastPage = 0;

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
      {blocks.map((b, animIdx) => {
        const pageBreak = b.page !== lastPage;
        lastPage = b.page;
        return (
          <div key={`${b.page}-${b.idx}`} className="animate-slide-in" style={{ animationDelay: `${Math.min(animIdx * 0.03, 0.5)}s` }}>
            {pageBreak && (
              <div data-page={b.page} className="flex items-center gap-3 mt-8 mb-4 scroll-mt-36">
                <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-white/60 backdrop-blur-sm border border-white/40 shadow-sm">
                  <IconPage /><span className="text-sm font-semibold text-violet-600">第 {b.page} 页</span>
                </div>
                <div className="flex-1 h-px bg-gradient-to-r from-violet-200/60 via-violet-100/30 to-transparent" />
              </div>
            )}
            <BlockItem b={b} taskId={taskId} />
          </div>
        );
      })}
    </div>
  );
}

