# HandOff
### Complete Build Guide — Windows & macOS
*Control your PC with hand gestures using your webcam*

**Stack:** Python · MediaPipe · OpenCV · pynput · Electron · React
**100% Open Source · 100% Local · No Backend**

---

## How HandOff Works

Before writing a single line of code, understand the architecture. There are two processes running on your machine at the same time:

| Process | Responsibility |
|---|---|
| Python Engine | Opens webcam, runs MediaPipe hand tracking, classifies gestures, fires mouse/keyboard events |
| Electron + React UI | Settings panel, gesture mapping editor, start/stop toggle, visual feedback |

They talk to each other via a local WebSocket — both running on the same machine, no internet involved.

> ✅ Everything is local. No cloud. No API keys. No data leaves your computer.

### The Data Flow

```
Webcam frame → MediaPipe (21 landmarks) → Gesture classifier → pynput → OS acts on it
```

Meanwhile, the Python engine broadcasts hand landmark data over WebSocket → React UI renders a live hand overlay so users can see what the app is tracking.

---

## Section 1 — Prerequisites

Install these tools before anything else. Do them in order.

### 1.1 Python 3.10+

Download from https://python.org/downloads — install version 3.10, 3.11, or 3.12. Do NOT use 3.13 (MediaPipe has not fully tested it yet).

> ⚠️ **Windows only:** During installation, check **"Add Python to PATH"**. Without this, every command below will fail.

Verify the install:

```bash
python --version
# Expected output: Python 3.10.x (or 3.11 / 3.12)
```

### 1.2 Node.js 18+

Download from https://nodejs.org — choose the LTS version.

```bash
node --version
# Expected: v18.x.x or higher

npm --version
# Expected: 9.x.x or higher
```

### 1.3 Git

- **Windows:** https://git-scm.com
- **macOS:** Run `git --version` in Terminal — it will prompt you to install Xcode Command Line Tools automatically.

### 1.4 A Code Editor

VS Code is recommended. Download from https://code.visualstudio.com

---

## Section 2 — Project Setup

### 2.1 Create the Folder Structure

Open a terminal, navigate to wherever you keep your projects, and run:

```bash
mkdir handoff
cd handoff
mkdir engine ui
```

Your project will have this shape:

```
handoff/
  engine/          ← Python: camera, hand tracking, input simulation
  ui/              ← Electron + React: settings panel
```

### 2.2 Set Up the Python Engine

Navigate into the engine folder and create a Python virtual environment:

```bash
cd engine

# Create virtual environment
python -m venv venv

# Activate it
# On Windows:
venv\Scripts\activate

# On macOS:
source venv/bin/activate

# Your terminal prompt should now show (venv)
```

> ⚠️ Every time you open a new terminal to work on the Python engine, you must activate the venv again.

Now install all Python dependencies:

```bash
pip install mediapipe opencv-python pynput websockets
```

What each package does:

- **mediapipe** — Google's hand tracking library. Detects 21 landmarks per hand in real time.
- **opencv-python** — Opens your webcam and reads frames.
- **pynput** — Simulates mouse movement, clicks, and keyboard input at the OS level.
- **websockets** — Lets the Python engine talk to the Electron UI over a local socket.

### 2.3 Set Up the Electron + React UI

```bash
cd ../ui
npm create vite@latest . -- --template react
npm install
npm install electron electron-builder concurrently wait-on
```

Open `ui/package.json` and add the following to the scripts section:

```json
"scripts": {
  "dev": "vite",
  "build": "vite build",
  "electron": "electron .",
  "start": "concurrently \"npm run dev\" \"wait-on http://localhost:5173 && electron .\"",
  "dist:win": "electron-builder --win",
  "dist:mac": "electron-builder --mac"
}
```

---

## Section 3 — Building the Python Engine

This is the core of HandOff. We build it in five files.

### 3.1 Hand Tracker — `tracker.py`

Create `engine/tracker.py`. This file opens the webcam and uses MediaPipe to detect hand landmarks.

```python
import cv2
import mediapipe as mp

class HandTracker:
    def __init__(self):
        self.mp_hands = mp.solutions.hands
        self.hands = self.mp_hands.Hands(
            static_image_mode=False,
            max_num_hands=1,
            min_detection_confidence=0.7,
            min_tracking_confidence=0.7
        )
        self.mp_draw = mp.solutions.drawing_utils

    def get_landmarks(self, frame):
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        result = self.hands.process(rgb)
        if result.multi_hand_landmarks:
            return result.multi_hand_landmarks[0].landmark
        return None
```

MediaPipe gives you 21 landmarks — each is an (x, y, z) point normalized between 0 and 1 relative to the frame. Landmark 8 is the tip of your index finger. Landmark 4 is the tip of your thumb.

### 3.2 Gesture Classifier — `gestures.py`

Create `engine/gestures.py`. This reads the raw landmarks and decides what gesture the user is making.

```python
def classify(landmarks, frame_w, frame_h):
    if not landmarks:
        return None, None

    # Get key points (normalized 0-1, multiply by frame size for pixels)
    index_tip = landmarks[8]
    thumb_tip  = landmarks[4]
    middle_tip = landmarks[12]
    ring_tip   = landmarks[16]
    wrist      = landmarks[0]

    # Convert to pixel coords
    ix, iy = int(index_tip.x * frame_w), int(index_tip.y * frame_h)
    tx, ty = int(thumb_tip.x * frame_w), int(thumb_tip.y * frame_h)

    # Pinch detection: distance between index tip and thumb tip
    pinch_dist = ((ix - tx)**2 + (iy - ty)**2) ** 0.5

    if pinch_dist < 40:
        return 'CLICK', (ix, iy)

    # Pointing: index up, others curled
    if (index_tip.y < landmarks[6].y and   # index extended
        middle_tip.y > landmarks[10].y and  # middle curled
        ring_tip.y > landmarks[14].y):      # ring curled
        return 'MOVE', (ix, iy)

    return None, (ix, iy)
```

> ⚠️ Start with just MOVE and CLICK. Get those working perfectly before adding scroll, swipe, or anything else. Premature complexity is how this project dies.

### 3.3 Input Controller — `controller.py`

Create `engine/controller.py`. This translates gestures into real OS input using pynput.

```python
import time
from pynput.mouse import Button, Controller as MouseController
import screeninfo

mouse = MouseController()

last_click_time = 0
CLICK_COOLDOWN = 0.3  # 300ms

def get_screen_size():
    monitor = screeninfo.get_monitors()[0]
    return monitor.width, monitor.height

def move_cursor(norm_x, norm_y):
    sw, sh = get_screen_size()
    mouse.position = (int(norm_x * sw), int(norm_y * sh))

def click():
    global last_click_time
    now = time.time()
    if now - last_click_time > CLICK_COOLDOWN:
        mouse.press(Button.left)
        mouse.release(Button.left)
        last_click_time = now

def scroll(direction):
    mouse.scroll(0, 3 if direction == 'up' else -3)
```

Install the extra package:

```bash
pip install screeninfo
```

### 3.4 WebSocket Server — `server.py`

Create `engine/server.py`. This broadcasts hand data to the Electron UI and receives commands back.

```python
import asyncio
import websockets
import json

clients = set()

async def handler(websocket):
    clients.add(websocket)
    try:
        async for message in websocket:
            pass  # Handle commands from UI here later
    finally:
        clients.discard(websocket)

async def broadcast(data):
    if clients:
        msg = json.dumps(data)
        await asyncio.gather(*[c.send(msg) for c in clients])

async def start_server():
    async with websockets.serve(handler, 'localhost', 8765):
        await asyncio.Future()  # run forever
```

### 3.5 Main Entry Point — `main.py`

Create `engine/main.py`. This wires everything together.

```python
import cv2
import asyncio
import threading
from tracker import HandTracker
from gestures import classify
from controller import move_cursor, click
from server import start_server, broadcast

tracker = HandTracker()
cap = cv2.VideoCapture(0)  # 0 = default webcam

# Run websocket server in a background thread
def run_ws():
    asyncio.run(start_server())

ws_thread = threading.Thread(target=run_ws, daemon=True)
ws_thread.start()

print('HandOff engine running. Press Q to quit.')

while True:
    ret, frame = cap.read()
    if not ret:
        break

    h, w = frame.shape[:2]
    landmarks = tracker.get_landmarks(frame)
    gesture, pos = classify(landmarks, w, h)

    if gesture == 'MOVE' and pos:
        move_cursor(pos[0] / w, pos[1] / h)

    elif gesture == 'CLICK':
        click()

    # Broadcast to UI
    if landmarks:
        points = [{'x': l.x, 'y': l.y} for l in landmarks]
        asyncio.run_coroutine_threadsafe(
            broadcast({'landmarks': points, 'gesture': gesture}),
            asyncio.get_event_loop()
        )

    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
```

Test the engine:

```bash
# Make sure venv is active first
cd engine
python main.py
```

> ✅ At this point your cursor should move when you point your index finger at the webcam, and click when you pinch. If it works, the hard part is done.

---

## Section 4 — Building the Electron UI

### 4.1 Electron Main Process — `electron/main.js`

Create `ui/electron/main.js`:

```javascript
const { app, BrowserWindow } = require('electron')
const path = require('path')

function createWindow() {
  const win = new BrowserWindow({
    width: 900,
    height: 600,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      nodeIntegration: false,
      contextIsolation: true
    }
  })

  if (process.env.NODE_ENV === 'development') {
    win.loadURL('http://localhost:5173')
  } else {
    win.loadFile(path.join(__dirname, '../dist/index.html'))
  }
}

app.whenReady().then(createWindow)
app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit()
})
```

### 4.2 Preload Script — `electron/preload.js`

```javascript
const { contextBridge } = require('electron')

contextBridge.exposeInMainWorld('handoff', {
  version: '1.0.0'
})
```

### 4.3 React App — `src/App.jsx`

Replace the default App.jsx:

```jsx
import { useState, useEffect } from 'react'

export default function App() {
  const [connected, setConnected] = useState(false)
  const [gesture, setGesture] = useState('None')
  const [landmarks, setLandmarks] = useState([])

  useEffect(() => {
    const ws = new WebSocket('ws://localhost:8765')

    ws.onopen = () => setConnected(true)
    ws.onclose = () => setConnected(false)
    ws.onmessage = (e) => {
      const data = JSON.parse(e.data)
      setGesture(data.gesture || 'None')
      setLandmarks(data.landmarks || [])
    }

    return () => ws.close()
  }, [])

  return (
    <div style={{ fontFamily: 'Arial', padding: 32 }}>
      <h1>HandOff</h1>
      <p>Engine: {connected ? '🟢 Connected' : '🔴 Disconnected'}</p>
      <p>Current gesture: <strong>{gesture}</strong></p>
      <p>Landmarks detected: {landmarks.length}</p>
    </div>
  )
}
```

To run both together:

```bash
# Terminal 1: Start Python engine
cd engine && source venv/bin/activate && python main.py

# Terminal 2: Start Electron UI
cd ui && npm run start
```

---

## Section 5 — Expanding the Gesture Library

Once MOVE and CLICK work, add these gestures one at a time. Test each before adding the next.

| Gesture | How to Detect It |
|---|---|
| Scroll Down | Index + middle fingers extended (peace sign), hand moving downward. Track Y position delta over 3 frames. |
| Scroll Up | Same peace sign, hand moving upward. |
| Right Click | Three fingers extended (index + middle + ring). Hold for 300ms. |
| Zoom In | Two hands detected, distance between index tips increasing. |
| Go Back | Open palm (all 5 fingers extended), swipe left quickly. |
| Thumb Up | Thumb extended upward, all other fingers curled. |

> ⚠️ Debounce every gesture with a 200-300ms cooldown. Without this, a single pinch fires 10 clicks per second. The debounce is already in `controller.py` from Section 3.3 — apply the same pattern to every gesture you add.

---

## Section 6 — Cursor Smoothing

Raw MediaPipe output is jittery. Your cursor will shake even when your hand is perfectly still. Fix this with a moving average.

Create `engine/smoother.py`:

```python
from collections import deque

class SmoothCursor:
    def __init__(self, buffer_size=5):
        self.xs = deque(maxlen=buffer_size)
        self.ys = deque(maxlen=buffer_size)

    def smooth(self, x, y):
        self.xs.append(x)
        self.ys.append(y)
        return sum(self.xs) / len(self.xs), sum(self.ys) / len(self.ys)
```

Use it in `main.py`:

```python
from smoother import SmoothCursor

smoother = SmoothCursor(buffer_size=6)

# Inside the while loop, replace the MOVE block:
if gesture == 'MOVE' and pos:
    smooth_x, smooth_y = smoother.smooth(pos[0] / w, pos[1] / h)
    move_cursor(smooth_x, smooth_y)
```

> ℹ️ `buffer_size=5` or `6` is the sweet spot. Too low = still jittery. Too high = cursor feels laggy.

---

## Section 7 — Packaging & Distribution

### 7.1 Bundle the Python Engine with PyInstaller

```bash
cd engine
pip install pyinstaller

pyinstaller --onefile --noconsole main.py --name handoff-engine

# Output is in engine/dist/
# Windows: handoff-engine.exe
# macOS:   handoff-engine
```

> ℹ️ `--noconsole` hides the terminal window on Windows. Remove it while debugging so you can see errors.

### 7.2 Configure Electron Builder

Add this to `ui/package.json`:

```json
"build": {
  "appId": "com.yourname.handoff",
  "productName": "HandOff",
  "extraResources": [
    {
      "from": "../engine/dist/",
      "to": "engine/",
      "filter": ["**/*"]
    }
  ],
  "win": {
    "target": "nsis",
    "icon": "assets/icon.ico"
  },
  "mac": {
    "target": "dmg",
    "icon": "assets/icon.icns"
  }
}
```

### 7.3 Spawn the Python Engine from Electron

Update `electron/main.js`:

```javascript
const { app, BrowserWindow } = require('electron')
const { spawn } = require('child_process')
const path = require('path')

let engineProcess = null

function startEngine() {
  const isWin = process.platform === 'win32'
  const engineName = isWin ? 'handoff-engine.exe' : 'handoff-engine'
  const enginePath = app.isPackaged
    ? path.join(process.resourcesPath, 'engine', engineName)
    : path.join(__dirname, '../../engine/dist', engineName)

  engineProcess = spawn(enginePath)
  engineProcess.stdout.on('data', d => console.log('Engine:', d.toString()))
  engineProcess.stderr.on('data', d => console.error('Engine error:', d.toString()))
}

app.whenReady().then(() => {
  startEngine()
  createWindow()
})

app.on('before-quit', () => {
  if (engineProcess) engineProcess.kill()
})
```

### 7.4 Build the Final Installers

```bash
# Step 1: Build the Python engine
cd engine && pyinstaller --onefile --noconsole main.py --name handoff-engine

# Step 2: Build the React app
cd ../ui && npm run build

# Step 3a: Package for Windows (run on Windows)
npm run dist:win
# Output: ui/dist/HandOff Setup 1.0.0.exe

# Step 3b: Package for macOS (run on macOS)
npm run dist:mac
# Output: ui/dist/HandOff-1.0.0.dmg
```

> ⚠️ You must build on the target platform. To get both `.exe` and `.dmg` you need to run the commands on a Windows machine and a Mac respectively. GitHub Actions can automate this.

---

## Section 8 — macOS Specific Setup

macOS requires explicit permission grants. Without these, the app silently fails.

### Permissions You Need

- **Camera access** — required for OpenCV to open the webcam
- **Accessibility access** — required for pynput to simulate mouse and keyboard input

Camera permission is triggered automatically when OpenCV first opens the webcam — macOS shows a popup. Accessibility is different.

### Granting Accessibility Permission

1. Open **System Settings → Privacy & Security → Accessibility**
2. Click the **+** button
3. Navigate to your HandOff app (or your terminal app during development) and add it
4. Toggle it **ON**

> ℹ️ During development, add your terminal app (Terminal.app or iTerm2) to Accessibility, not the Python script itself.

### macOS Gatekeeper

If you distribute the app without an Apple Developer certificate, macOS blocks it with *"App can't be opened because it is from an unidentified developer"*. The user can bypass this by right-clicking the app → Open → Open anyway. For your portfolio, this is fine. For real distribution, you need a paid Apple Developer account ($99/year) to sign and notarize the app.

---

## Section 9 — Recording the Demo

The demo video is more important than the code. A recruiter will watch it before they look at a single line of your repo.

**What to show:**

- Open the HandOff app — show the clean settings UI
- Open a browser with YouTube or Instagram visible
- Point your index finger — cursor moves
- Pinch — it clicks, video plays
- Peace sign moving down — page scrolls
- Keep your hands clearly visible the whole time

> ℹ️ Keep it under 90 seconds. No talking required. Add a lo-fi track underneath.

**Recording tools:**

- **Windows:** OBS Studio (free) — records webcam and screen simultaneously
- **macOS:** OBS Studio or QuickTime + iMovie to merge tracks

---

## Quick Reference

### All Commands

```bash
# ── Setup ──────────────────────────────────────────────────────
cd engine && python -m venv venv
source venv/bin/activate              # macOS
venv\Scripts\activate                 # Windows
pip install mediapipe opencv-python pynput websockets screeninfo pyinstaller

cd ../ui
npm create vite@latest . -- --template react && npm install
npm install electron electron-builder concurrently wait-on

# ── Development ─────────────────────────────────────────────────
# Terminal 1:
cd engine && source venv/bin/activate && python main.py

# Terminal 2:
cd ui && npm run start

# ── Build & Package ─────────────────────────────────────────────
cd engine && pyinstaller --onefile --noconsole main.py --name handoff-engine
cd ../ui && npm run build
npm run dist:win     # on Windows → .exe
npm run dist:mac     # on macOS  → .dmg
```

### Complete File Structure

```
handoff/
├── engine/
│   ├── venv/                  ← Python virtual env (don't commit to git)
│   ├── dist/                  ← PyInstaller output
│   ├── main.py                ← Entry point
│   ├── tracker.py             ← MediaPipe hand tracking
│   ├── gestures.py            ← Gesture classification
│   ├── controller.py          ← pynput input simulation
│   ├── smoother.py            ← Cursor smoothing
│   └── server.py              ← WebSocket server
└── ui/
    ├── electron/
    │   ├── main.js            ← Electron main process
    │   └── preload.js         ← Preload script
    ├── src/
    │   └── App.jsx            ← React settings panel
    ├── assets/
    │   ├── icon.ico           ← Windows icon
    │   └── icon.icns          ← macOS icon
    └── package.json
```

### MediaPipe Landmark Index

| Index | Landmark |
|---|---|
| 0 | Wrist |
| 4 | Thumb tip |
| 8 | Index finger tip |
| 12 | Middle finger tip |
| 16 | Ring finger tip |
| 20 | Pinky tip |
| 5, 9, 13, 17 | Finger base knuckles (MCP joints) |
| 6, 10, 14, 18 | Middle knuckles (PIP joints) |

---

*Build it. Ship it. Demo it. The recruiter reaction you're going for is the mouse stopping mid-scroll.*
