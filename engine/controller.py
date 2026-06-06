import time
from pynput.mouse import Button, Controller as MouseController
from pynput.keyboard import Key, Controller as KeyboardController
import screeninfo

mouse    = MouseController()
keyboard = KeyboardController()

last_click_time  = 0
last_rclick_time = 0
CLICK_COOLDOWN   = 0.3


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


def right_click():
    global last_rclick_time
    now = time.time()
    if now - last_rclick_time > CLICK_COOLDOWN:
        mouse.press(Button.right)
        mouse.release(Button.right)
        last_rclick_time = now


def double_click():
    mouse.press(Button.left)
    mouse.release(Button.left)
    time.sleep(0.05)
    mouse.press(Button.left)
    mouse.release(Button.left)


def swipe_left():
    with keyboard.pressed(Key.alt):
        keyboard.press(Key.left)
        keyboard.release(Key.left)


def swipe_right():
    with keyboard.pressed(Key.alt):
        keyboard.press(Key.right)
        keyboard.release(Key.right)


def zoom_in():
    with keyboard.pressed(Key.ctrl):
        keyboard.press('=')
        keyboard.release('=')


def zoom_out():
    with keyboard.pressed(Key.ctrl):
        keyboard.press('-')
        keyboard.release('-')


def scroll(direction):
    mouse.scroll(0, 3 if direction == 'up' else -3)


def tab_right():
    with keyboard.pressed(Key.alt):
        keyboard.press(Key.tab)
        keyboard.release(Key.tab)


def tab_left():
    with keyboard.pressed(Key.alt):
        with keyboard.pressed(Key.shift):
            keyboard.press(Key.tab)
            keyboard.release(Key.tab)
