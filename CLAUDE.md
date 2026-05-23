# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Architecture

Two processes communicate over a local WebSocket (`ws://localhost:8765`). No internet, no cloud, no API keys.

```
Webcam → MediaPipe (21 landmarks) → gestures.py → pynput → OS
                                  ↓
                            WebSocket broadcast → React UI (live overlay)
```

| Process | Path | Stack |
|---|---|---|
| Python engine | `engine/` | Python 3.10–3.12, MediaPipe, OpenCV, pynput, websockets |
| Electron UI | `ui/` | Electron, React (Vite), WebSocket client |

Python 3.13 is incompatible with MediaPipe — do not use it.

## Engine file roles

- `main.py` — entry point; wires tracker → classifier → controller → WebSocket broadcast
- `tracker.py` — opens webcam via OpenCV, runs MediaPipe, returns 21 normalized landmarks
- `gestures.py` — classifies landmarks into gesture names (MOVE, CLICK, etc.) and pixel position
- `controller.py` — translates gestures to OS input via pynput; has 300ms click cooldown
- `smoother.py` — moving average (deque, buffer=5–6) to reduce landmark jitter
- `server.py` — asyncio WebSocket server; broadcasts to all connected clients

## Dev commands

**Python engine** (venv must be active — required every new terminal):

```bash
cd engine
venv\Scripts\activate          # Windows
source venv/bin/activate       # macOS

python main.py                 # run engine (press Q to quit)
```

**Electron UI:**

```bash
cd ui
npm run start                  # runs Vite dev server + Electron concurrently
```

**Both together (two terminals):**

```powershell
# Terminal 1 (Windows PowerShell)
cd engine; .\venv\Scripts\python.exe main.py

# Terminal 2
cd ui; npm run start
```

## Setup (first time)

```bash
cd engine
python -m venv venv
venv\Scripts\activate
pip install mediapipe opencv-python pynput websockets screeninfo pyinstaller

cd ../ui
npm create vite@latest . -- --template react && npm install
npm install electron electron-builder concurrently wait-on
```

## Build & package

```bash
# 1. Bundle Python engine
cd engine
pyinstaller --onefile --noconsole main.py --name handoff-engine
# Output: engine/dist/handoff-engine.exe (Win) or handoff-engine (mac)

# 2. Build React
cd ../ui && npm run build

# 3. Package installer (must run on target platform)
npm run dist:win    # → ui/dist/HandOff Setup 1.0.0.exe
npm run dist:mac    # → ui/dist/HandOff-1.0.0.dmg
```

Remove `--noconsole` from PyInstaller when debugging to see engine errors.

## Key landmarks (MediaPipe indices)

| Index | Point |
|---|---|
| 0 | Wrist |
| 4 | Thumb tip |
| 8 | Index tip |
| 12 | Middle tip |
| 16 | Ring tip |
| 6, 10, 14, 18 | PIP (middle) knuckles — used to detect finger curl |

Curl check: finger is curled when `tip.y > pip.y` (landmarks are normalized 0–1, y increases downward).

## Gesture expansion rules

- Add gestures one at a time, fully tested before the next.
- Every gesture needs a cooldown (200–300ms). Pattern is already in `controller.py` — copy it.
- Start with MOVE + CLICK; scroll, right-click, zoom come after.

## macOS permissions

pynput requires Accessibility permission — add terminal app to **System Settings → Privacy & Security → Accessibility** during development. Camera permission is auto-prompted by OpenCV on first run.

## .gitignore essentials

```
engine/venv/
engine/dist/
ui/node_modules/
ui/dist/
```
