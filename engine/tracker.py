import os
import urllib.request
import cv2
import mediapipe as mp
from mediapipe.tasks import python
from mediapipe.tasks.python import vision

MODEL_PATH = os.path.join(os.path.dirname(__file__), 'hand_landmarker.task')
MODEL_URL = (
    'https://storage.googleapis.com/mediapipe-models/'
    'hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task'
)


class HandTracker:
    def __init__(self):
        if not os.path.exists(MODEL_PATH):
            print('Downloading hand landmarker model (~1 MB)...')
            urllib.request.urlretrieve(MODEL_URL, MODEL_PATH)
            print('Model ready.')

        options = vision.HandLandmarkerOptions(
            base_options=python.BaseOptions(model_asset_path=MODEL_PATH),
            num_hands=1,
            min_hand_detection_confidence=0.7,
            min_hand_presence_confidence=0.7,
            min_tracking_confidence=0.7,
        )
        self.detector = vision.HandLandmarker.create_from_options(options)

    def get_landmarks(self, frame):
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        result = self.detector.detect(mp_image)
        if result.hand_landmarks:
            return result.hand_landmarks[0]
        return None
