export interface TaskInfo {
  task_id: string;
  filename: string;
  status: 'pending' | 'translating' | 'completed' | 'failed';
  page_count: number;
  progress: { current: number; total: number };
  quality: { total_blocks: number; pass_rate: string } | null;
  error: string;
}

export interface BlockData {
  page: number;
  idx: number;
  type: string;
  en: string;
  zh: string;
  bbox?: number[];
  verified?: boolean;
}

export interface WsEvent {
  type: 'start' | 'page_start' | 'block_done' | 'figure' |
        'page_done' | 'quality' | 'complete' | 'error';
  [key: string]: unknown;
}

export type AppMode = 'upload' | 'translating' | 'done';
