import asyncio
import json
import threading
import websockets

clients  = set()
paused   = False

# Shared latest payload — main thread writes, asyncio sender reads
_latest  = None
_lock    = threading.Lock()


def set_payload(data):
    global _latest
    with _lock:
        _latest = data


async def handler(websocket):
    global paused
    clients.add(websocket)
    print(f'[WS] client connected ({len(clients)} total)')
    try:
        async for message in websocket:
            try:
                cmd = json.loads(message).get('cmd')
                if cmd == 'pause':
                    paused = True
                elif cmd == 'resume':
                    paused = False
            except Exception:
                pass
    finally:
        clients.discard(websocket)
        print(f'[WS] client disconnected ({len(clients)} remaining)')


async def _sender():
    """Asyncio task: sends latest payload to all clients at ~30 fps."""
    while True:
        await asyncio.sleep(0.033)
        if not clients:
            continue
        with _lock:
            data = _latest
        if data is None:
            continue
        msg  = json.dumps(data)
        for c in list(clients):
            try:
                await c.send(msg)
            except Exception:
                clients.discard(c)


async def start_server():
    async with websockets.serve(handler, 'localhost', 8765):
        print('[WS] server listening on ws://localhost:8765')
        await _sender()   # runs forever
