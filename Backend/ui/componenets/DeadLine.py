"""
DeadLine.py

Replaces the old Unity DeadPixelSpawner: draws a full-length dead
pixel line across a monitor as its own always-on-top window. Clicking
the line destroys it.

Server.py emits deadline_signals.spawn_requested when a response's
ACTION is DEADPIXEL (cross-thread safe, same pattern as
avatar_signals). DeadLineManager lives on the Qt main thread and owns
the windows.

The window is wider than the visible line: the extra strip is painted
with alpha 1 so it still catches mouse clicks (fully transparent
pixels would let clicks fall through to whatever is underneath).
"""

import random

from PyQt6.QtCore import Qt, QObject, pyqtSignal
from PyQt6.QtGui import QColor, QPainter
from PyQt6.QtWidgets import QApplication, QWidget

LINE_THICKNESS = 2
HIT_THICKNESS = 12
MAX_LINES = 5
LINE_COLORS = ["#ff0000", "#00ff00", "#0000ff", "#ffffff", "#ff00ff", "#00ffff"]
EDGE_MARGIN = 40


class _DeadLineSignals(QObject):
    spawn_requested = pyqtSignal()


deadline_signals = _DeadLineSignals()


class DeadLineWindow(QWidget):

    closed = pyqtSignal(object)

    def __init__(self, screen_geometry, vertical, offset, color):
        super().__init__()
        print("Dead line summon")
        self._vertical = vertical
        self._color = QColor(color)

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        if vertical:
            self.setGeometry(
                screen_geometry.left() + offset - HIT_THICKNESS // 2,
                screen_geometry.top(),
                HIT_THICKNESS,
                screen_geometry.height(),
            )
        else:
            self.setGeometry(
                screen_geometry.left(),
                screen_geometry.top() + offset - HIT_THICKNESS // 2,
                screen_geometry.width(),
                HIT_THICKNESS,
            )

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 1))

        center = (HIT_THICKNESS - LINE_THICKNESS) // 2

        if self._vertical:
            painter.fillRect(center, 0, LINE_THICKNESS, self.height(), self._color)
        else:
            painter.fillRect(0, center, self.width(), LINE_THICKNESS, self._color)

        painter.end()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.close()
            event.accept()
            return

        super().mousePressEvent(event)

    def closeEvent(self, event):
        self.closed.emit(self)
        super().closeEvent(event)


class DeadLineManager(QObject):

    def __init__(self):
        super().__init__()
        self._windows = []
        deadline_signals.spawn_requested.connect(self.spawn)

    def spawn(self):
        screens = QApplication.screens()
        if not screens:
            return

        geometry = random.choice(screens).geometry()
        vertical = random.random() < 0.5

        span = geometry.width() if vertical else geometry.height()
        offset = random.randint(EDGE_MARGIN, max(EDGE_MARGIN, span - EDGE_MARGIN))

        window = DeadLineWindow(geometry, vertical, offset, random.choice(LINE_COLORS))
        window.closed.connect(self._on_closed)
        self._windows.append(window)
        window.show()

        if len(self._windows) > MAX_LINES:
            self._windows[0].close()

    def _on_closed(self, window):
        if window in self._windows:
            self._windows.remove(window)