const BASE = 'http://localhost:7860';

export async function uploadPdf(file: File) {
  const form = new FormData();
  form.append('file', file);
  const res = await fetch(`${BASE}/api/upload`, { method: 'POST', body: form });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function startTranslation(taskId: string, dpi = 144) {
  const res = await fetch(`${BASE}/api/translate/${taskId}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ dpi }),
  });
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
