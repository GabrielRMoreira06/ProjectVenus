import os
import sys

import keyboard
import qtawesome as qta
from PyQt6.QtCore import Qt, QTimer, QSize, pyqtSignal
from PyQt6.QtGui import QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QFrame,
)

from ui.MessageComposer import MessageComposer
from ui.PanelWindow import PanelWindow, DraggableFrame, _load_oxanium_family
from ui.Theme import PINK, PINK_SOFT, BG_DARK, BG_PANEL, BG_BUBBLE


class InputWindow(DraggableFrame):

    toggle_requested = pyqtSignal()

    def __init__(self, process_question, on_open=None, on_close=None):
        super().__init__()

        self.on_open = on_open or (lambda: None)
        self.on_close = on_close or (lambda: None)

        self._positioned = False
        self.font_family = _load_oxanium_family()

        self.setWindowTitle("Talk to Venus")
        self.setWindowFlags(
            Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setFixedSize(440, 260)

        self.toggle_requested.connect(self.toggle)

        self.setStyleSheet(f"""
            DraggableFrame {{
                background-color: {BG_DARK};
                border: 1px solid {PINK};
                border-radius: 14px;
                color: white;
                font-family: "{self.font_family}";
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 14)
        layout.setSpacing(10)

        layout.addLayout(self._build_header())

        self.composer = MessageComposer(
            process_question,
            compact=False,
            placeholder="Say something to Venus... (Ctrl+V pastes text/image, Enter sends)",
        )
        self.composer.send_started.connect(self.hide_window)
        layout.addWidget(self.composer, stretch=1)

        # Escape key closes window
        QShortcut(QKeySequence(Qt.Key.Key_Escape), self, activated=self.hide_window)

    def _build_header(self):
        header = QHBoxLayout()
        header.setSpacing(8)

        icon_label = QLabel()
        icon_label.setPixmap(qta.icon("fa5s.comment-dots", color=PINK).pixmap(QSize(16, 16)))
        icon_label.setStyleSheet("border: none; background: transparent;")

        title_label = QLabel("Talk to Venus")
        title_label.setStyleSheet("color: white; font-size: 14px; font-weight: bold; border: none; background: transparent;")

        header.addWidget(icon_label)
        header.addWidget(title_label)
        header.addStretch()

        close_button = QPushButton()
        close_button.setIcon(qta.icon("fa5s.times", color=PINK_SOFT, color_active="white"))
        close_button.setIconSize(QSize(14, 14))
        close_button.setFixedSize(28, 28)
        close_button.setCursor(Qt.CursorShape.PointingHandCursor)
        close_button.clicked.connect(self.hide_window)
        close_button.setStyleSheet(f"""
            QPushButton {{
                background-color: #16051a;
                border: 1px solid {PINK};
                border-radius: 8px;
                color: {PINK_SOFT};
            }}
            QPushButton:hover {{
                background-color: {PINK};
                color: white;
            }}
        """)
        header.addWidget(close_button)

        return header

    # ------------------------------------------------------------------
    # Show/hide
    # ------------------------------------------------------------------

    def show_window(self):
        if not self._positioned:
            screen = QApplication.primaryScreen().availableGeometry()
            self.move(screen.center().x() - self.width() // 2, screen.height() - self.height() - 60)
            self._positioned = True

        self.show()
        self.raise_()
        self.activateWindow()
        QTimer.singleShot(0, self.composer.reset)

        self.on_open()

    def hide_window(self):
        self.hide()
        self.on_close()

    def toggle(self):
        if self.isVisible():
            self.hide_window()
        else:
            self.show_window()


def start_input_window(process_question, on_open=None, on_close=None, hotkey="ctrl+alt+t", open_automatically=False):
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    window = InputWindow(process_question, on_open=on_open, on_close=on_close)

    keyboard.add_hotkey(hotkey, window.toggle_requested.emit)
    print(f"[text_input_window] Hotkey '{hotkey}' registered globally.")

    panel_window = PanelWindow(process_question)
    keyboard.add_hotkey("ctrl+alt+h", panel_window.toggle_requested.emit)
    print("[text_input_window] Hotkey 'ctrl+alt+h' registered globally (PanelWindow).")

    if open_automatically:
        QTimer.singleShot(500, window.show_window)

    sys.exit(app.exec())