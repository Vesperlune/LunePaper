const BASE = 'http://localhost:7860';

export async function uploadPdf(file: File) {
  const form = new FormData();
  form.append('file', file);
  const res = await fetch(`${BASE}/api/upload`, { method: 'POST', body: form });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export interface OcrModelInfo {
  id: string;
  name: string;
  description: string;
  vram_estimate_mb: number;
  is_default: boolean;
  available: boolean;
}

export async function getOcrModels(): Promise<OcrModelInfo[]> {
  const res = await fetch(`${BASE}/api/ocr-models`);
  if (!res.ok) return [];
  return res.json();
}

export async function startTranslation(
  taskId: string,
  dpi = 144,
  startPage = 0,
  endPage: number | null = null,
  ocrModel?: string
) {
  const payload: Record<string, unknown> = { dpi, start_page: startPage };
  if (endPage !== null) payload.end_page = endPage;
  if (ocrModel) payload.ocr_model = ocrModel;

  const res = await fetch(`${BASE}/api/translate/${taskId}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function cancelTranslation(taskId: string) {
  const res = await fetch(`${BASE}/api/cancel/${taskId}`, { method: 'POST' });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function getStatus(taskId: string) {
  const res = await fetch(`${BASE}/api/status/${taskId}`);
  return res.json();
}

export function getDownloadUrl(taskId: string) {
  return `${BASE}/api/download/${taskId}`;
}

export function getImageUrl(taskId: string, figureName: string) {
  return `${BASE}/api/image/${taskId}/${figureName}`;
}

export function createWs(taskId: string): WebSocket {
  return new WebSocket(`ws://localhost:7860/ws/${taskId}`);
}

export interface HistoryItem {
  task_id: string;
  filename: string;
  page_count: number;
  created_at: number;
  quality: { total_blocks?: number; pass_rate?: string };
  status: string;
}

export async function listHistory(): Promise<HistoryItem[]> {
  const res = await fetch(`${BASE}/api/history`);
  if (!res.ok) return [];
  return res.json();
}

export async function loadHistoryTask(taskId: string) {
  const res = await fetch(`${BASE}/api/history/${taskId}/load`, { method: 'POST' });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function deleteHistoryTask(taskId: string) {
  const res = await fetch(`${BASE}/api/history/${taskId}`, { method: 'DELETE' });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}
