export interface TaskInfo {
  task_id: string;
  filename: string;
  status: 'pending' | 'translating' | 'completed' | 'failed';
  page_count: number;
  progress: { current: number; total: number };
  quality: { total_blocks: number; pass_rate: string } | null;
  error: string;
  tldr?: PaperTLDR;
}

export interface PaperTLDR {
  background?: string;   // 研究背景与痛点
  method?: string;       // 核心创新与方案
  metrics?: string;      // 实验性能与指标
  conclusion?: string;   // 工作价值与结论
}

export interface VariableOccurrence {
  page: number;
  blockIdx: number;
  formulaLatex: string;
}

export interface GlobalVariableItem {
  symbol: string;        // e.g. "$Q$", "$d_k$"
  cleanSymbol: string;   // e.g. "Q", "d_k"
  name: string;          // e.g. "Query Matrix (查询矩阵)"
  desc: string;          // e.g. "Pack of query vectors..."
  occurrences: VariableOccurrence[];
  count: number;
}

export interface ReferenceItem {
  id: string;          // e.g. "1", "12"
  page: number;        // page number in document
  idx: number;         // block index in page
  raw: string;         // full reference text
  authors?: string;    // e.g. "Jimmy Lei Ba, Jamie Ryan Kiros et al."
  title?: string;      // e.g. "Layer normalization"
  venueYear?: string;  // e.g. "arXiv:1607.06450, 2016"
  year?: string;       // e.g. "2016"
  arxivId?: string;    // e.g. "1607.06450"
}

export interface VariableInfo {
  symbol: string;      // e.g. "$Q$", "$d_k$"
  name: string;        // e.g. "Query Matrix", "Dimension"
  desc: string;        // contextual explanation extracted from text
}

export interface BlockData {
  page: number;
  idx: number;
  type: string;
  en: string;
  zh: string;
  bbox?: number[];
  verified?: boolean;
  figure_id?: string;
  passthrough?: boolean;
}

export interface WsEvent {
  type: 'start' | 'phase' | 'ocr_progress' | 'ocr_page_blocks' |
        'translate_progress' | 'page_start' | 'block_done' | 'figure' |
        'page_done' | 'quality' | 'complete' | 'error';
  [key: string]: unknown;
}

export type AppMode = 'upload' | 'translating' | 'done';
