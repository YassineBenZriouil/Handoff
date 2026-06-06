import sys
import os
import cv2
import time
import subprocess
import winreg
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'engine'))

from PySide6.QtWidgets import QApplication, QWidget, QLabel, QPushButton, QVBoxLayout, QHBoxLayout
from PySide6.QtCore import Qt, QThread, Signal, QTimer
from PySide6.QtGui import QImage, QPixmap, QPainter, QPen, QColor, QFont

from tracker import HandTracker
from gestures import classify_all
from controller import (move_cursor, click, right_click, double_click,
                        swipe_left, swipe_right, zoom_in, zoom_out, scroll,
                        tab_right, tab_left)
from smoother import SmoothCursor

SAFE_PROCESSES = {'electron.exe', 'node.exe', 'code.exe', 'explorer.exe'}
_OWN_PID = os.getpid()

GESTURE_LABELS = {
    'CLICK':        '🤏 Click',
    'RIGHT_CLICK':  '🖱️ Right Click',
    'DOUBLE_CLICK': '🤏🤏 Double Click',
    'SWIPE_LEFT':   '👈 Swipe Left',
    'SWIPE_RIGHT':  '👉 Swipe Right',
    'ZOOM_IN':      '🔍 Zoom In',
    'ZOOM_OUT':     '🔎 Zoom Out',
    'SCROLL_UP':    '⬆️ Scroll Up',
    'SCROLL_DOWN':  '⬇️ Scroll Down',
    'TAB_RIGHT':    '➡️ Next Window',
    'TAB_LEFT':     '⬅️ Prev Window',
    'MOVE':         '☝️ Move',
}

# Color per hand: hand 0 = green, hand 1 = cyan
HAND_COLORS = ['#4ade80', '#22d3ee']

CONNECTIONS = [
    (0,1),(1,2),(2,3),(3,4),
    (0,5),(5,6),(6,7),(7,8),
    (0,9),(9,10),(10,11),(11,12),
    (0,13),(13,14),(14,15),(15,16),
    (0,17),(17,18),(18,19),(19,20),
    (5,9),(9,13),(13,17),
]

DISPATCH = {
    'SWIPE_LEFT':  swipe_left,
    'SWIPE_RIGHT': swipe_right,
    'ZOOM_IN':     zoom_in,
    'ZOOM_OUT':    zoom_out,
    'SCROLL_UP':   lambda: scroll('up'),
    'SCROLL_DOWN': lambda: scroll('down'),
    'RIGHT_CLICK': right_click,
    'TAB_RIGHT':   tab_right,
    'TAB_LEFT':    tab_left,
}


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
                if exe_name not in SAFE_PROCESSES and exe_name != 'python.exe':
                    r = subprocess.run(['taskkill', '/F', '/IM', exe_name], capture_output=True)
                    if r.returncode == 0:
                        print(f'Killed {exe_name} (was holding camera)', flush=True)
        except (OSError, FileNotFoundError):
            pass
        i += 1
    winreg.CloseKey(key)


def _try_open(idx, backend=cv2.CAP_DSHOW):
    label = 'DSHOW' if backend == cv2.CAP_DSHOW else 'MSMF'
    print(f'[CAM] Trying index {idx} ({label})...', flush=True)
    cap = cv2.VideoCapture(idx, backend)
    print(f'[CAM] Index {idx} opened={cap.isOpened()}', flush=True)
    if not cap.isOpened():
        cap.release()
        return None
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    ret, _ = cap.read()
    print(f'[CAM] Index {idx} read={ret}', flush=True)
    if ret:
        return cap
    cap.release()
    return None


def open_camera():
    for backend, label in ((cv2.CAP_DSHOW, 'DSHOW'), (cv2.CAP_MSMF, 'MSMF')):
        print(f'[CAM] Scanning via {label}...', flush=True)
        for idx in range(3):
            cap = _try_open(idx, backend)
            if cap:
                print(f'Camera ready at index {idx} ({label})', flush=True)
                return cap

    print('[CAM] All failed — killing camera holders and retrying...', flush=True)
    kill_camera_users()
    time.sleep(1.0)

    for backend, label in ((cv2.CAP_DSHOW, 'DSHOW'), (cv2.CAP_MSMF, 'MSMF')):
        for idx in range(3):
            cap = _try_open(idx, backend)
            if cap:
                print(f'Camera ready at index {idx} ({label}) after kill', flush=True)
                return cap

    print('[CAM] Camera unavailable', flush=True)
    return None


FRAME_INTERVAL = 1.0 / 30


class EngineThread(QThread):
    # frame(np), hands(list of landmark lists), gestures(list of (gesture, pos))
    frame_ready = Signal(object, list, list)

    def __init__(self):
        super().__init__()
        self.paused = False
        self._running = True
        self.tracker = HandTracker()
        self.smoother = SmoothCursor(buffer_size=6)

    def run(self):
        cap = open_camera()
        fail_count = 0
        frame_count = 0
        fps_t = time.time()
        last_emit = 0.0

        while self._running:
            if cap is None:
                print('[DEBUG] No camera — retrying in 2s', flush=True)
                for _ in range(20):  # 2s in 100ms chunks — interruptible
                    if not self._running:
                        return
                    time.sleep(0.1)
                cap = open_camera()
                continue

            ret, frame = cap.read()
            if not ret:
                fail_count += 1
                if fail_count >= 30:
                    print('[DEBUG] Lost feed after 30 failures — reopening')
                    cap.release()
                    cap = None
                    fail_count = 0
                else:
                    time.sleep(0.033)
                continue

            fail_count = 0

            now = time.time()
            if now - last_emit < FRAME_INTERVAL:
                continue
            last_emit = now

            h, w = frame.shape[:2]
            hands = self.tracker.get_all_landmarks(frame)
            gestures = classify_all(hands, w, h)

            if not self.paused:
                moved = False
                for i, (gesture, pos) in enumerate(gestures):
                    if gesture == 'MOVE' and pos and not moved:
                        sx, sy = self.smoother.smooth(pos[0] / w, pos[1] / h)
                        move_cursor(sx, sy)
                        moved = True
                    elif gesture == 'CLICK':
                        click()
                    elif gesture in DISPATCH:
                        DISPATCH[gesture]()

            self.frame_ready.emit(frame.copy(), hands, gestures)

            frame_count += 1
            if frame_count % 30 == 0:
                elapsed = time.time() - fps_t
                total_lm = sum(len(h) for h in hands)
                g_str = ', '.join(g for g, _ in gestures if g) or 'none'
                print(f'[DEBUG] {30/elapsed:.1f} fps | {len(hands)} hand(s) | {total_lm} lm | {g_str}')
                fps_t = time.time()

        if cap:
            cap.release()

    def stop(self):
        self._running = False
        self.wait()


class CameraView(QLabel):
    def __init__(self):
        super().__init__()
        self.setMinimumSize(640, 480)
        self.setAlignment(Qt.AlignCenter)
        self.setStyleSheet('background: #0a0a0a;')
        self.setAttribute(Qt.WA_OpaquePaintEvent, True)
        self._hands = []
        self._pixmap = None
        self._rgb = None

    def update_frame(self, frame, hands):
        self._hands = hands or []
        self._rgb = np.ascontiguousarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
        h, w = self._rgb.shape[:2]
        img = QImage(self._rgb.data, w, h, self._rgb.strides[0], QImage.Format_RGB888)
        self._pixmap = QPixmap.fromImage(img)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        if self._pixmap:
            scaled = self._pixmap.scaled(self.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
            x_off = (self.width() - scaled.width()) // 2
            y_off = (self.height() - scaled.height()) // 2
            painter.drawPixmap(x_off, y_off, scaled)

            pw = scaled.width()
            ph = scaled.height()

            for hand_idx, landmarks in enumerate(self._hands):
                color = HAND_COLORS[hand_idx % len(HAND_COLORS)]

                pen = QPen(QColor(color), 2)
                painter.setPen(pen)
                for a, b in CONNECTIONS:
                    if a < len(landmarks) and b < len(landmarks):
                        la, lb = landmarks[a], landmarks[b]
                        painter.drawLine(
                            int(la.x * pw) + x_off, int(la.y * ph) + y_off,
                            int(lb.x * pw) + x_off, int(lb.y * ph) + y_off,
                        )

                for i, lm in enumerate(landmarks):
                    x = int(lm.x * pw) + x_off
                    y = int(lm.y * ph) + y_off
                    if i == 8:
                        painter.setBrush(QColor('#facc15'))
                        r = 7
                    elif i == 4:
                        painter.setBrush(QColor('#f87171'))
                        r = 7
                    else:
                        painter.setBrush(QColor(color))
                        r = 4
                    painter.setPen(Qt.NoPen)
                    painter.drawEllipse(x - r, y - r, r * 2, r * 2)
        else:
            painter.setPen(QColor('#555'))
            painter.setFont(QFont('Arial', 14))
            painter.drawText(self.rect(), Qt.AlignCenter, 'Waiting for camera...')


class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('HandOff')
        # Never steal keyboard focus — pynput keys go to the app the user is actually using
        self.setWindowFlags(
            Qt.Window |
            Qt.WindowStaysOnTopHint |
            Qt.WindowDoesNotAcceptFocus
        )
        self.setStyleSheet('''
            QWidget { background: #111; color: #eee; font-family: Arial; }
            QPushButton {
                background: #1e40af; color: white; border: none;
                padding: 8px 20px; border-radius: 6px; font-size: 13px;
            }
            QPushButton:hover { background: #2563eb; }
            QPushButton:disabled { background: #333; color: #666; }
            QLabel#status_on  { color: #4ade80; font-size: 13px; }
            QLabel#status_off { color: #f87171; font-size: 13px; }
            QLabel#gesture    { color: #a78bfa; font-size: 14px; }
        ''')

        self.camera_view = CameraView()

        self.status_label = QLabel('● Starting...')
        self.status_label.setObjectName('status_off')

        self.gesture_label = QLabel('—')
        self.gesture_label.setObjectName('gesture')

        self.pause_btn = QPushButton('⏸ Pause')
        self.pause_btn.clicked.connect(self.toggle_pause)

        header = QHBoxLayout()
        title = QLabel('HandOff')
        title.setStyleSheet('font-size: 20px; font-weight: bold; color: white;')
        header.addWidget(title)
        header.addStretch()
        header.addWidget(self.status_label)
        header.addWidget(self.pause_btn)

        footer = QHBoxLayout()
        footer.addWidget(self.gesture_label)
        footer.addStretch()
        self.lm_label = QLabel('No hands')
        self.lm_label.setStyleSheet('color: #888; font-size: 12px;')
        footer.addWidget(self.lm_label)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)
        layout.addLayout(header)
        layout.addWidget(self.camera_view, 1)
        layout.addLayout(footer)

        self._flash_timer = QTimer()
        self._flash_timer.setSingleShot(True)
        self._flash_timer.timeout.connect(lambda: self.gesture_label.setText('—'))

        self.engine = EngineThread()
        self.engine.frame_ready.connect(self.on_frame)
        self.engine.start()

        self.status_label.setText('● Running')
        self.status_label.setObjectName('status_on')

    def on_frame(self, frame, hands, gestures):
        self.camera_view.update_frame(frame, hands)

        total_lm = sum(len(h) for h in hands)
        self.lm_label.setText(f'{len(hands)} hand(s) · {total_lm} lm' if hands else 'No hands')

        notable = next(
            (g for g, _ in gestures if g and g != 'MOVE'),
            None
        )
        if notable:
            self.gesture_label.setText(GESTURE_LABELS.get(notable, notable))
            self._flash_timer.start(900)

    def toggle_pause(self):
        self.engine.paused = not self.engine.paused
        if self.engine.paused:
            self.pause_btn.setText('▶ Resume')
            self.pause_btn.setStyleSheet('background: #166534; color: white; border: none; padding: 8px 20px; border-radius: 6px; font-size: 13px;')
        else:
            self.pause_btn.setText('⏸ Pause')
            self.pause_btn.setStyleSheet('background: #1e40af; color: white; border: none; padding: 8px 20px; border-radius: 6px; font-size: 13px;')

    def closeEvent(self, event):
        self.engine.stop()
        event.accept()


if __name__ == '__main__':
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    win = MainWindow()
    win.resize(720, 560)
    win.show()
    sys.exit(app.exec())
