import random

import win32con
import win32gui
from PyQt6.QtCore import Qt, QObject, QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
)

NOTE_WIDTH = 260
MAX_NOTES = 5
EDGE_MARGIN = 60
PAPER = "#F8C8DC"
BORDER = "#F0B2C9"
INK = "#3a2a1a"
FONT = "Segoe Print"


class _StickyNoteSignals(QObject):
    spawn_requested = pyqtSignal(str)


sticky_note_signals = _StickyNoteSignals()


class StickyNoteWindow(QWidget):

    closed = pyqtSignal(object)

    def __init__(self, text):
        super().__init__()
        self._drag_offset = None

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnBottomHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setFixedWidth(NOTE_WIDTH)
        self.setStyleSheet(
            f"StickyNoteWindow {{ background-color: {PAPER}; border: 1px solid {BORDER}; }}"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 8, 14, 12)
        layout.setSpacing(6)

        top = QHBoxLayout()
        top.addStretch()
        close_button = QPushButton("✕")
        close_button.setFixedSize(20, 20)
        close_button.setCursor(Qt.CursorShape.PointingHandCursor)
        close_button.setStyleSheet(
            f"QPushButton {{ background: transparent; border: none; color: {INK}; }}"
            "QPushButton:hover { color: #b00020; }"
        )
        close_button.clicked.connect(self.close)
        top.addWidget(close_button)
        layout.addLayout(top)

        body = QLabel(text)
        body.setWordWrap(True)
        body.setStyleSheet(
            f"color: {INK}; font-family: '{FONT}'; font-size: 14px; background: transparent;"
        )
        layout.addWidget(body)

        signature = QLabel("— Venus ♥")
        signature.setAlignment(Qt.AlignmentFlag.AlignRight)
        signature.setStyleSheet(
            f"color: {INK}; font-family: '{FONT}'; font-size: 12px; background: transparent;"
        )
        layout.addWidget(signature)

        self.adjustSize()

    def place_randomly(self, geometry):
        min_x = geometry.left() + EDGE_MARGIN
        max_x = max(min_x, geometry.right() - self.width() - EDGE_MARGIN)
        min_y = geometry.top() + EDGE_MARGIN
        max_y = max(min_y, geometry.bottom() - self.height() - EDGE_MARGIN)
        self.move(random.randint(min_x, max_x), random.randint(min_y, max_y))

    def send_to_bottom(self):
        try:
            win32gui.SetWindowPos(
                int(self.winId()), win32con.HWND_BOTTOM, 0, 0, 0, 0,
                win32con.SWP_NOMOVE | win32con.SWP_NOSIZE | win32con.SWP_NOACTIVATE,
            )
        except Exception:
            pass

    def showEvent(self, event):
        super().showEvent(event)
        QTimer.singleShot(0, self.send_to_bottom)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag_offset is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_offset)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._drag_offset = None
        self.send_to_bottom()
        super().mouseReleaseEvent(event)

    def closeEvent(self, event):
        self.closed.emit(self)
        super().closeEvent(event)


class StickyNoteManager(QObject):

    def __init__(self):
        super().__init__()
        self._windows = []
        sticky_note_signals.spawn_requested.connect(self.spawn)

    def spawn(self, text):
        text = (text or "").strip()
        if not text:
            return

        screen = QApplication.primaryScreen()
        if screen is None:
            return

        window = StickyNoteWindow(text)
        window.place_randomly(screen.availableGeometry())
        window.closed.connect(self._on_closed)
        self._windows.append(window)
        window.show()

        if len(self._windows) > MAX_NOTES:
            self._windows[0].close()

    def _on_closed(self, window):
        if window in self._windows:
            self._windows.remove(window)