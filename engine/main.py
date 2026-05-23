import cv2
import asyncio
import threading
import time
import os
import subprocess
import winreg
import base64
from tracker import HandTracker
from gestures import classify
from controller import move_cursor, click, swipe_left, swipe_right, zoom_in, zoom_out
from smoother import SmoothCursor
from server import start_server, set_payload
import server as srv

SAFE_PROCESSES = {'electron.exe', 'node.exe', 'code.exe', 'python.exe', 'explorer.exe'}


def kill_camera_users():
    key_path = (
        r'SOFTWARE\Microsoft\Windows\CurrentVersion'
        r'\CapabilityAccessManager\ConsentStore\webcam\NonPackaged'
    )
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path)
    except OSError:
        return
    i = 0
    while True:
        try:
            sub_name = winreg.EnumKey(key, i)
        except OSError:
            break
        try:
            sub_key = winreg.OpenKey(key, sub_name)
            stop, _ = winreg.QueryValueEx(sub_key, 'LastUsedTimeStop')
            winreg.CloseKey(sub_key)
            if stop == 0:
                exe_name = os.path.basename(sub_name.replace('#', os.sep)).lower()
                if exe_name not in SAFE_PROCESSES:
                    r = subprocess.run(['taskkill', '/F', '/IM', exe_name], capture_output=True)
                    if r.returncode == 0:
                        print(f'Killed {exe_name} (was holding camera)')
        except (OSError, FileNotFoundError):
            pass
        i += 1
    winreg.CloseKey(key)


def open_camera():
    backends = [cv2.CAP_DSHOW, cv2.CAP_MSMF, 0]  # 0 = default
    for idx in range(3):
        for backend in backends:
            print(f'Trying camera index {idx} backend {backend}...')
            cap = cv2.VideoCapture(idx, backend) if backend else cv2.VideoCapture(idx)
            if not cap.isOpened():
                cap.release()
                continue
            cap.set(cv2.CAP_PROP_FRAME_WIDTH,  640)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
            cap.set(cv2.CAP_PROP_FPS, 30)
            # Try reading a few frames — some drivers need a moment
            for attempt in range(10):
                ret, frame = cap.read()
                if ret:
                    print(f'Camera ready: index={idx} backend={backend} attempt={attempt}')
                    return cap
                time.sleep(0.05)
            cap.release()

    print('Camera busy — killing holders and retrying...')
    kill_camera_users()
    time.sleep(1.5)

    for idx in range(3):
        cap = cv2.VideoCapture(idx, cv2.CAP_DSHOW)
        if cap.isOpened():
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
            for _ in range(10):
                ret, _ = cap.read()
                if ret:
                    print(f'Camera ready after kill: index={idx}')
                    return cap
                time.sleep(0.05)
            cap.release()

    return None   # caller handles None — engine still runs, just no camera


# ── Start WebSocket server first so UI can connect immediately ────────────────
loop = asyncio.new_event_loop()


def run_ws():
    asyncio.set_event_loop(loop)
    loop.run_until_complete(start_server())


ws_thread = threading.Thread(target=run_ws, daemon=True)
ws_thread.start()
time.sleep(0.3)  # give server a moment to bind

# ── Init ML + camera ─────────────────────────────────────────────────────────
tracker  = HandTracker()
smoother = SmoothCursor(buffer_size=6)
cap      = open_camera()

if cap is None:
    print('ERROR: No camera found. Engine running without camera — UI will stay blank.')
else:
    print('HandOff engine running. Ctrl+C to quit.')

GESTURE_ACTIONS = {
    'SWIPE_LEFT':  swipe_left,
    'SWIPE_RIGHT': swipe_right,
    'ZOOM_IN':     zoom_in,
    'ZOOM_OUT':    zoom_out,
}

frame_count = 0
fail_count  = 0
last_stat   = time.time()

try:
    while cap is not None:
        ret, frame = cap.read()
        if not ret:
            fail_count += 1
            print(f'cap.read() failed ({fail_count})')
            if fail_count >= 30:
                print('ERROR: Lost webcam feed.')
                break
            time.sleep(0.05)
            continue
        fail_count   = 0
        frame_count += 1

        now = time.time()
        if now - last_stat >= 3:
            print(f'Running — {frame_count} frames/3s | {len(srv.clients)} client(s) connected')
            frame_count = 0
            last_stat   = now

        h, w = frame.shape[:2]
        landmarks = tracker.get_landmarks(frame)
        gesture, pos = classify(landmarks, w, h)

        if not srv.paused:
            if gesture == 'MOVE' and pos:
                sx, sy = smoother.smooth(pos[0] / w, pos[1] / h)
                move_cursor(sx, sy)
            elif gesture == 'CLICK':
                click()
            elif gesture in GESTURE_ACTIONS:
                GESTURE_ACTIONS[gesture]()

        _, buf    = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 55])
        frame_b64 = base64.b64encode(buf).decode('utf-8')
        points    = [{'x': l.x, 'y': l.y} for l in landmarks] if landmarks else []

        set_payload({
            'frame':     frame_b64,
            'landmarks': points,
            'gesture':   gesture,
            'paused':    srv.paused,
        })

except KeyboardInterrupt:
    print('Stopping.')
finally:
    if cap:
        cap.release()
