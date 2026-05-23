import time
from collections import deque

_wrist_xs = deque(maxlen=12)
_spreads  = deque(maxlen=6)
_last_swipe_time = 0.0
_last_zoom_time  = 0.0

SWIPE_THRESHOLD = 0.18
SWIPE_COOLDOWN  = 0.7
ZOOM_THRESHOLD  = 0.05
ZOOM_COOLDOWN   = 0.5


def classify(landmarks, frame_w, frame_h):
    global _last_swipe_time, _last_zoom_time

    if not landmarks:
        _wrist_xs.clear()
        _spreads.clear()
        return None, None

    index_tip  = landmarks[8]
    thumb_tip  = landmarks[4]
    middle_tip = landmarks[12]
    ring_tip   = landmarks[16]
    wrist      = landmarks[0]

    ix = int(index_tip.x * frame_w)
    iy = int(index_tip.y * frame_h)
    tx = int(thumb_tip.x * frame_w)
    ty = int(thumb_tip.y * frame_h)

    pinch_dist = ((ix - tx) ** 2 + (iy - ty) ** 2) ** 0.5
    now = time.time()

    # CLICK — thumb+index pinch
    if pinch_dist < 40:
        _wrist_xs.clear()
        return 'CLICK', (ix, iy)

    _wrist_xs.append(wrist.x)

    # SWIPE — wrist moves horizontally across 10+ frames
    if len(_wrist_xs) >= 10 and now - _last_swipe_time > SWIPE_COOLDOWN:
        delta = _wrist_xs[-1] - _wrist_xs[0]
        if abs(delta) > SWIPE_THRESHOLD:
            _last_swipe_time = now
            _wrist_xs.clear()
            return ('SWIPE_RIGHT' if delta > 0 else 'SWIPE_LEFT'), (ix, iy)

    # ZOOM — peace sign (index+middle extended, ring curled), track spread
    index_ext = index_tip.y < landmarks[6].y
    middle_ext = middle_tip.y < landmarks[10].y
    ring_curl  = ring_tip.y > landmarks[14].y

    if index_ext and middle_ext and ring_curl:
        spread = ((index_tip.x - middle_tip.x) ** 2 +
                  (index_tip.y - middle_tip.y) ** 2) ** 0.5
        _spreads.append(spread)

        if len(_spreads) >= 5 and now - _last_zoom_time > ZOOM_COOLDOWN:
            delta = _spreads[-1] - _spreads[0]
            if abs(delta) > ZOOM_THRESHOLD:
                _last_zoom_time = now
                _spreads.clear()
                return ('ZOOM_IN' if delta > 0 else 'ZOOM_OUT'), (ix, iy)
    else:
        _spreads.clear()

    # MOVE — index extended, middle + ring curled
    if (index_tip.y < landmarks[6].y and
            middle_tip.y > landmarks[10].y and
            ring_tip.y > landmarks[14].y):
        return 'MOVE', (ix, iy)

    return None, (ix, iy)
