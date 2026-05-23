from collections import deque


class SmoothCursor:
    def __init__(self, buffer_size=6):
        self.xs = deque(maxlen=buffer_size)
        self.ys = deque(maxlen=buffer_size)

    def smooth(self, x, y):
        self.xs.append(x)
        self.ys.append(y)
        return sum(self.xs) / len(self.xs), sum(self.ys) / len(self.ys)
