import time
from collections import deque

PINCH_DIST       = 40
SWIPE_THRESHOLD  = 0.18
SWIPE_COOLDOWN   = 0.7
ZOOM_THRESHOLD   = 0.05
ZOOM_COOLDOWN    = 0.5
SCROLL_THRESHOLD = 0.10
SCROLL_COOLDOWN  = 0.35
TAB_THRESHOLD    = 0.09   # normalized x delta while pinching to trigger tab switch
TAB_COOLDOWN     = 0.5


def _new_state():
    return {
        'wrist_xs':    deque(maxlen=12),
        'wrist_ys':    deque(maxlen=10),
        'spreads':     deque(maxlen=6),
        'last_swipe':  0.0,
        'last_zoom':   0.0,
        'last_scroll': 0.0,
        'last_rclick': 0.0,
        'last_tab':    0.0,
        'pinch_active': False,
        'pinch_start_x': 0.0,
        'pinch_moved':  False,  # True once tab gesture fired — suppresses click
    }


_hand_states = [_new_state(), _new_state()]


def _classify_hand(landmarks, frame_w, frame_h, state):
    index_tip  = landmarks[8]
    thumb_tip  = landmarks[4]
    middle_tip = landmarks[12]
    ring_tip   = landmarks[16]
    pinky_tip  = landmarks[20]
    wrist      = landmarks[0]

    ix = int(index_tip.x * frame_w)
    iy = int(index_tip.y * frame_h)
    tx = int(thumb_tip.x * frame_w)
    ty = int(thumb_tip.y * frame_h)
    rx = int(ring_tip.x * frame_w)
    ry = int(ring_tip.y * frame_h)
    now = time.time()

    index_ext  = index_tip.y  < landmarks[6].y
    middle_ext = middle_tip.y < landmarks[10].y
    ring_curl  = ring_tip.y   > landmarks[14].y
    pinky_curl = pinky_tip.y  > landmarks[18].y

    # CLICK / TAB_SWITCH — index+thumb pinch
    # Pinch + hold + slide right/left → TAB_RIGHT / TAB_LEFT (suppresses further clicks)
    # Pinch without slide → CLICK (controller cooldown handles dedup)
    if ((ix - tx)**2 + (iy - ty)**2)**0.5 < PINCH_DIST:
        if not state['pinch_active']:
            state['pinch_active'] = True
            state['pinch_moved'] = False
            state['pinch_start_x'] = index_tip.x
        pdelta = index_tip.x - state['pinch_start_x']
        if not state['pinch_moved'] and abs(pdelta) > TAB_THRESHOLD and now - state['last_tab'] > TAB_COOLDOWN:
            state['pinch_moved'] = True
            state['last_tab'] = now
            state['wrist_xs'].clear()
            state['wrist_ys'].clear()
            return ('TAB_RIGHT' if pdelta > 0 else 'TAB_LEFT'), (ix, iy)
        if state['pinch_moved']:
            return None, (ix, iy)  # tab already fired, suppress click
        state['wrist_xs'].clear()
        state['wrist_ys'].clear()
        return 'CLICK', (ix, iy)
    else:
        state['pinch_active'] = False
        state['pinch_moved'] = False

    # RIGHT_CLICK — ring+thumb pinch
    if (((rx - tx)**2 + (ry - ty)**2)**0.5 < PINCH_DIST
            and now - state['last_rclick'] > 0.3):
        state['last_rclick'] = now
        state['wrist_xs'].clear()
        state['wrist_ys'].clear()
        return 'RIGHT_CLICK', (rx, ry)

    state['wrist_xs'].append(wrist.x)
    state['wrist_ys'].append(wrist.y)

    # SWIPE — horizontal wrist delta over 10 frames
    if len(state['wrist_xs']) >= 10 and now - state['last_swipe'] > SWIPE_COOLDOWN:
        delta = state['wrist_xs'][-1] - state['wrist_xs'][0]
        if abs(delta) > SWIPE_THRESHOLD:
            state['last_swipe'] = now
            state['wrist_xs'].clear()
            return ('SWIPE_RIGHT' if delta > 0 else 'SWIPE_LEFT'), (ix, iy)

    # SCROLL — V-sign (index+middle up, ring+pinky curled) + vertical wrist
    if (index_ext and middle_ext and ring_curl and pinky_curl
            and len(state['wrist_ys']) >= 8
            and now - state['last_scroll'] > SCROLL_COOLDOWN):
        ydelta = state['wrist_ys'][-1] - state['wrist_ys'][0]
        if abs(ydelta) > SCROLL_THRESHOLD:
            state['last_scroll'] = now
            state['wrist_ys'].clear()
            return ('SCROLL_DOWN' if ydelta > 0 else 'SCROLL_UP'), (ix, iy)

    # ZOOM — V-sign, track finger spread (ring may be extended; only index+middle matter)
    if index_ext and middle_ext and ring_curl:
        spread = ((index_tip.x - middle_tip.x)**2 +
                  (index_tip.y - middle_tip.y)**2)**0.5
        state['spreads'].append(spread)
        if len(state['spreads']) >= 5 and now - state['last_zoom'] > ZOOM_COOLDOWN:
            delta = state['spreads'][-1] - state['spreads'][0]
            if abs(delta) > ZOOM_THRESHOLD:
                state['last_zoom'] = now
                state['spreads'].clear()
                return ('ZOOM_IN' if delta > 0 else 'ZOOM_OUT'), (ix, iy)
    else:
        state['spreads'].clear()

    # MOVE — index extended, middle+ring curled
    if (index_ext
            and middle_tip.y > landmarks[10].y
            and ring_tip.y   > landmarks[14].y):
        return 'MOVE', (ix, iy)

    return None, (ix, iy)


def classify_all(hands, frame_w, frame_h):
    """Returns list of (gesture, pos) — one entry per detected hand."""
    if not hands:
        for s in _hand_states:
            s['wrist_xs'].clear()
            s['wrist_ys'].clear()
            s['spreads'].clear()
        return []
    results = []
    for i, landmarks in enumerate(hands):
        state = _hand_states[i] if i < len(_hand_states) else _new_state()
        results.append(_classify_hand(landmarks, frame_w, frame_h, state))
    return results


def classify(landmarks, frame_w, frame_h):
    """Single-hand backward-compat wrapper."""
    if not landmarks:
        return None, None
    r = classify_all([landmarks], frame_w, frame_h)
    return r[0] if r else (None, None)
