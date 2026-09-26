import qtawesome as qta
from PyQt6.QtCore import Qt, QTimer, QSize, pyqtSignal
from PyQt6.QtGui import QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QApplication, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton,
)

from ui.MessageComposer import MessageComposer
from ui.PanelWindow import PanelWindow, DraggableFrame
from ui.Constants import load_oxanium_family
import ui.Theme as Theme


class InputWindow(DraggableFrame):

    toggle_requested = pyqtSignal()

    def __init__(self, process_question, on_open=None, on_close=None):
        super().__init__()

        self.on_open = on_open or (lambda: None)
        self.on_close = on_close or (lambda: None)

        self._positioned = False
        self._font_family = load_oxanium_family()

        self.setObjectName("inputWindow")
        self.setWindowTitle("Talk to Venus")
        self.setWindowFlags(
            Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setFixedSize(440, 260)

        self.toggle_requested.connect(self.toggle)

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

        QShortcut(QKeySequence(Qt.Key.Key_Escape), self, activated=self.hide_window)

        # Applied here (not left for a later theme change) so the window
        # is styled correctly the moment it's constructed — see the same
        # fix in PanelWindow._on_theme_changed.
        self._apply_style()
        Theme.theme_signals.changed.connect(self._apply_style)

    def _apply_style(self):
        self.setStyleSheet(f"""
            #inputWindow {{
                background-color: {Theme.BG_PANEL};
                border: 1px solid {Theme.PINK};
                border-radius: 18px;
                font-family: "{self._font_family}";
            }}
        """)
        self._icon_label.setPixmap(qta.icon("fa5s.comment-dots", color=Theme.PINK).pixmap(QSize(16, 16)))
        self._title_label.setStyleSheet(
            "color: white; font-size: 15px; font-weight: bold; border: none; background: transparent;")
        self._apply_close_button_style()

    def _apply_close_button_style(self):
        self._close_button.setIcon(qta.icon("fa5s.times", color=Theme.PINK_SOFT, color_active="white"))
        self._close_button.setStyleSheet(f"""
            QPushButton {{
                background-color: #16051a;
                border: 1px solid {Theme.PINK};
                border-radius: 10px;
                color: {Theme.PINK_SOFT};
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {Theme.PINK};
                color: white;
            }}
        """)

    def _build_header(self):
        header = QHBoxLayout()
        header.setSpacing(8)

        self._icon_label = QLabel()
        self._icon_label.setStyleSheet("border: none; background: transparent;")

        self._title_label = QLabel("Talk to Venus")

        header.addWidget(self._icon_label)
        header.addWidget(self._title_label)
        header.addStretch()

        self._close_button = QPushButton()
        self._close_button.setIconSize(QSize(14, 14))
        self._close_button.setFixedSize(28, 28)
        self._close_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._close_button.clicked.connect(self.hide_window)
        header.addWidget(self._close_button)

        return header

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