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
from gestures import classify
from controller import move_cursor, click, swipe_left, swipe_right, zoom_in, zoom_out
from smoother import SmoothCursor

SAFE_PROCESSES = {'electron.exe', 'node.exe', 'code.exe', 'python.exe', 'explorer.exe'}

GESTURE_LABELS = {
    'CLICK':       '🤏 Click',
    'SWIPE_LEFT':  '👈 Swipe Left',
    'SWIPE_RIGHT': '👉 Swipe Right',
    'ZOOM_IN':     '🔍 Zoom In',
    'ZOOM_OUT':    '🔎 Zoom Out',
    'MOVE':        '☝️ Move',
}

CONNECTIONS = [
    (0,1),(1,2),(2,3),(3,4),
    (0,5),(5,6),(6,7),(7,8),
    (0,9),(9,10),(10,11),(11,12),
    (0,13),(13,14),(14,15),(15,16),
    (0,17),(17,18),(18,19),(19,20),
    (5,9),(9,13),(13,17),
]


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
    for idx in range(3):
        cap = cv2.VideoCapture(idx, cv2.CAP_DSHOW)
        if not cap.isOpened():
            cap.release()
            continue
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        ret, _ = cap.read()
        if ret:
            print(f'Camera ready at index {idx}')
            return cap
        cap.release()

    kill_camera_users()
    time.sleep(1.0)
    cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
    if cap.isOpened():
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        ret, _ = cap.read()
        if ret:
            return cap
    cap.release()
    return None


class EngineThread(QThread):
    frame_ready = Signal(object, object, str)  # frame(np), landmarks, gesture

    def __init__(self):
        super().__init__()
        self.paused = False
        self._running = True
        self.tracker = HandTracker()
        self.smoother = SmoothCursor(buffer_size=6)

    def run(self):
        cap = open_camera()
        fail_count = 0

        while self._running:
            if cap is None:
                time.sleep(2.0)
                cap = open_camera()
                continue

            ret, frame = cap.read()
            if not ret:
                fail_count += 1
                if fail_count >= 30:
                    print('Lost webcam feed — recovering...')
                    cap.release()
                    cap = None
                    fail_count = 0
                else:
                    time.sleep(0.033)
                continue

            fail_count = 0
            h, w = frame.shape[:2]
            landmarks = self.tracker.get_landmarks(frame)
            gesture, pos = classify(landmarks, w, h)

            if not self.paused:
                if gesture == 'MOVE' and pos:
                    sx, sy = self.smoother.smooth(pos[0] / w, pos[1] / h)
                    move_cursor(sx, sy)
                elif gesture == 'CLICK':
                    click()
                elif gesture in ('SWIPE_LEFT', 'SWIPE_RIGHT', 'ZOOM_IN', 'ZOOM_OUT'):
                    {'SWIPE_LEFT': swipe_left, 'SWIPE_RIGHT': swipe_right,
                     'ZOOM_IN': zoom_in, 'ZOOM_OUT': zoom_out}[gesture]()

            self.frame_ready.emit(frame, landmarks, gesture or '')

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
        self._landmarks = []
        self._pixmap = None

    def update_frame(self, frame, landmarks):
        self._landmarks = landmarks or []
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb.shape
        img = QImage(rgb.data, w, h, ch * w, QImage.Format_RGB888)
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

            if self._landmarks:
                pw = scaled.width()
                ph = scaled.height()

                pen = QPen(QColor('#4ade80'), 2)
                painter.setPen(pen)
                for a, b in CONNECTIONS:
                    if a < len(self._landmarks) and b < len(self._landmarks):
                        la, lb = self._landmarks[a], self._landmarks[b]
                        painter.drawLine(
                            int(la.x * pw) + x_off, int(la.y * ph) + y_off,
                            int(lb.x * pw) + x_off, int(lb.y * ph) + y_off,
                        )

                for i, lm in enumerate(self._landmarks):
                    x = int(lm.x * pw) + x_off
                    y = int(lm.y * ph) + y_off
                    if i == 8:
                        painter.setBrush(QColor('#facc15'))
                        r = 7
                    elif i == 4:
                        painter.setBrush(QColor('#f87171'))
                        r = 7
                    else:
                        painter.setBrush(QColor('white'))
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
        self.setStyleSheet('''
            QWidget { background: #111; color: #eee; font-family: Arial; }
            QPushButton {
                background: #1e40af; color: white; border: none;
                padding: 8px 20px; border-radius: 6px; font-size: 13px;
            }
            QPushButton:hover { background: #2563eb; }
            QPushButton.paused { background: #166534; }
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
        lm_label = QLabel('landmarks: —')
        lm_label.setStyleSheet('color: #888; font-size: 12px;')
        self.lm_label = lm_label
        footer.addWidget(lm_label)

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

    def on_frame(self, frame, landmarks, gesture):
        self.camera_view.update_frame(frame, landmarks)
        lm_count = len(landmarks) if landmarks else 0
        self.lm_label.setText(f'{lm_count} landmarks' if lm_count else 'No hand')

        if gesture and gesture != 'MOVE':
            label = GESTURE_LABELS.get(gesture, gesture)
            self.gesture_label.setText(label)
            self._flash_timer.start(900)
        elif not gesture:
            pass  # let flash timer clear it

    def toggle_pause(self):
        self.engine.paused = not self.engine.paused
        if self.engine.paused:
            self.pause_btn.setText('▶ Resume')
            self.pause_btn.setProperty('class', 'paused')
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
