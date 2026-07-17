import { useEffect, useRef, useCallback } from 'react';
import { createWs } from '../api';

// eslint-disable-next-line @typescript-eslint/no-explicit-any
export function useWebSocket(
  taskId: string | null,
  onEvent: (e: any) => void,
) {
  const wsRef = useRef<WebSocket | null>(null);
  const onEventRef = useRef(onEvent);
  onEventRef.current = onEvent;

  useEffect(() => {
    if (!taskId) return;
    const ws = createWs(taskId);
    wsRef.current = ws;

    ws.onmessage = (msg) => {
      try {
        const event: WsEvent = JSON.parse(msg.data);
        onEventRef.current(event);
      } catch { /* ignore */ }
    };

    return () => { ws.close(); };
  }, [taskId]);

  const send = useCallback((data: object) => {
    wsRef.current?.send(JSON.stringify(data));
  }, []);

  return { send };
}
