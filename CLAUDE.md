# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Architecture

Single Python process. Camera owned exclusively by Python — no conflict.

```
Webcam → OpenCV (DSHOW) → MediaPipe (21 landmarks) → gestures.py → pynput → OS
                                                    ↓
                                          EngineThread (QThread) → PySide6 window
```

| Path | Stack |
|---|---|
| `engine/` | Python 3.10–3.12, MediaPipe, OpenCV, pynput, screeninfo |
| `ui/` | PySide6 — imports engine modules directly, no WebSocket |

Python 3.13 is incompatible with MediaPipe — do not use it.

## File roles

### engine/
- `tracker.py` — opens webcam via OpenCV (CAP_DSHOW), runs MediaPipe Tasks API, returns 21 normalized landmarks
- `gestures.py` — classifies landmarks into gesture names (MOVE, CLICK, RIGHT_CLICK, SWIPE_LEFT, SWIPE_RIGHT, ZOOM_IN, ZOOM_OUT, SCROLL_UP, SCROLL_DOWN); per-hand state; `classify_all(hands, w, h)` for 2-hand support
- `controller.py` — translates gestures to OS input via pynput; 300ms click cooldown
- `smoother.py` — moving average (deque, buffer=6) to reduce landmark jitter
- `server.py` — legacy WebSocket server (unused in pyui; kept for future headless mode)
- `main.py` — legacy entry point for headless/WebSocket mode

### ui/
- `main.py` — entry point; `EngineThread(QThread)` runs camera+ML+gestures, emits `frame_ready` signal; `CameraView(QLabel)` paints frames + skeleton overlay; pause button flips flag in same process

## Dev commands

**Run the app (one terminal):**

```powershell
cd pyui
npm run dev
# equivalent: ..\engine\venv\Scripts\python.exe main.py
```

**Terminal Keeper** (auto-launches on IDE open via `.vscode/sessions.json`):
- HandOff terminal → `cd pyui && npm run dev`
- Claude terminal → `claude`

## Setup (first time)

```powershell
cd engine
python -m venv venv
.\venv\Scripts\activate
pip install mediapipe opencv-python pynput screeninfo PySide6
```

## Build & package

```powershell
# Bundle into single exe
cd engine
pyinstaller --onefile --noconsole ..\pyui\main.py --name handoff --paths .
# Output: engine/dist/handoff.exe
```

Remove `--noconsole` when debugging to see errors.

## Key landmarks (MediaPipe indices)

| Index | Point |
|---|---|
| 0 | Wrist |
| 4 | Thumb tip |
| 8 | Index tip |
| 12 | Middle tip |
| 16 | Ring tip |
| 6, 10, 14, 18 | PIP (middle) knuckles — used to detect finger curl |

Curl check: finger is curled when `tip.y > pip.y` (normalized 0–1, y increases downward).

## Gesture expansion rules

- Add gestures one at a time, fully tested before the next.
- Every gesture needs a cooldown (200–300ms). Copy pattern from `controller.py`.
- Gestures: MOVE (index up), CLICK (index+thumb pinch), RIGHT_CLICK (ring+thumb pinch), SWIPE (wrist X delta > 0.18/10 frames), ZOOM (V-sign spread delta > 0.05/5 frames), SCROLL (V-sign + wrist Y delta > 0.10/8 frames).

## Camera notes

- Always use `cv2.CAP_DSHOW` on Windows — more stable, avoids conflicts
- Set `cv2.CAP_PROP_BUFFERSIZE = 1` to reduce latency
- `open_camera()` in ui/main.py auto-kills processes holding camera via registry, then retries
- Engine auto-recovers if feed drops (30 consecutive read failures → reopen)

## macOS permissions

pynput requires Accessibility permission — add terminal to **System Settings → Privacy & Security → Accessibility**. Camera auto-prompted by OpenCV on first run.

## .gitignore essentials

```
engine/venv/
engine/dist/
engine/__pycache__/
engine/*.task
ui/node_modules/
ui/dist/
```
