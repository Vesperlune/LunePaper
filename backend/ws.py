"""WebSocket handler for real-time progress streaming."""
import json, asyncio
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from backend.worker import get_event_queue

router = APIRouter()


@router.websocket("/ws/{task_id}")
async def websocket_endpoint(ws: WebSocket, task_id: str):
    await ws.accept()
    queue = get_event_queue(task_id)

    try:
        while True:
            # Check client messages (ping/pong or unsubscribe)
            try:
                msg = await asyncio.wait_for(ws.receive_text(), timeout=0.1)
                data = json.loads(msg)
                if data.get("type") == "unsubscribe":
                    break
            except asyncio.TimeoutError:
                pass

            # Drain event queue
            while not queue.empty():
                event = queue.get_nowait()
                await ws.send_json(event)

                if event["type"] in ("complete", "error"):
                    # Send final event, then close
                    await asyncio.sleep(0.5)
                    return

            await asyncio.sleep(0.2)

    except WebSocketDisconnect:
        pass
    except Exception:
        pass
