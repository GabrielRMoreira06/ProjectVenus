"""
Notepad.py

Simple floating text editor window — New/Open/Save/Save As on a plain
QTextEdit. Same frameless DraggableFrame + Theme styling pattern as
InputWindow/PanelWindow, and the same toggle_requested signal, so it
plugs into TextInput.py's hotkey registration the same way PanelWindow
does. No connection to Orchestrator/GeminiWorker — just a scratchpad.
"""

import os
from pathlib import Path

import qtawesome as qta
from PyQt6.QtCore import Qt, QSize, pyqtSignal
from PyQt6.QtGui import QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QApplication, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QTextEdit, QFileDialog,
)

from ui.PanelWindow import DraggableFrame
from ui.Constants import load_oxanium_family
import ui.Theme as Theme


class NotepadWindow(DraggableFrame):

    toggle_requested = pyqtSignal()

    def __init__(self):
        super().__init__()

        self._positioned = False
        self.current_file_path = None
        self.font_family = load_oxanium_family()

        self.setWindowTitle("Notepad")
        self.setWindowFlags(
            Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.resize(520, 420)

        self.toggle_requested.connect(self.toggle)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 14)
        layout.setSpacing(10)

        layout.addLayout(self._build_header())

        self.text_edit = QTextEdit()
        self.text_edit.setAcceptRichText(False)
        layout.addWidget(self.text_edit, stretch=1)

        QShortcut(QKeySequence("Ctrl+S"), self, activated=self.save_file)
        QShortcut(QKeySequence("Ctrl+Shift+S"), self, activated=self.save_file_as)
        QShortcut(QKeySequence("Ctrl+O"), self, activated=self.open_file)
        QShortcut(QKeySequence("Ctrl+N"), self, activated=self.new_file)
        QShortcut(QKeySequence(Qt.Key.Key_Escape), self, activated=self.hide_window)

        self._apply_style()
        Theme.theme_signals.changed.connect(self._apply_style)

    # ------------------------------------------------------------------
    # Header
    # ------------------------------------------------------------------

    def _build_header(self):
        header = QHBoxLayout()
        header.setSpacing(8)

        self._icon_label = QLabel()
        self._icon_label.setStyleSheet("border: none; background: transparent;")

        self.title_label = QLabel("Notepad")
        self.title_label.setStyleSheet(
            "color: white; font-size: 14px; font-weight: bold; border: none; background: transparent;"
        )

        header.addWidget(self._icon_label)
        header.addWidget(self.title_label)
        header.addStretch()

        self.new_button = self._make_icon_button("fa5s.file")
        self.new_button.clicked.connect(self.new_file)

        self.open_button = self._make_icon_button("fa5s.folder-open")
        self.open_button.clicked.connect(self.open_file)

        self.save_button = self._make_icon_button("fa5s.save")
        self.save_button.clicked.connect(self.save_file)

        self.close_button = self._make_icon_button("fa5s.times")
        self.close_button.clicked.connect(self.hide_window)

        for button in (self.new_button, self.open_button, self.save_button, self.close_button):
            header.addWidget(button)

        return header

    def _make_icon_button(self, icon_name):
        button = QPushButton()
        button.setIconSize(QSize(14, 14))
        button.setFixedSize(28, 28)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setProperty("icon_name", icon_name)
        return button

    # ------------------------------------------------------------------
    # File operations
    # ------------------------------------------------------------------

    def new_file(self):
        self.text_edit.clear()
        self.current_file_path = None
        self._update_title()

    def open_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Open file", "", "Text Files (*.txt);;All Files (*)"
        )
        if not path:
            return

        try:
            content = Path(path).read_text(encoding="utf-8")
        except OSError as error:
            self.title_label.setText(f"Notepad — failed to open: {error}")
            return

        self.text_edit.setPlainText(content)
        self.current_file_path = path
        self._update_title()

    def save_file(self):
        if self.current_file_path is None:
            self.save_file_as()
            return

        self._write_to(self.current_file_path)

    def save_file_as(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Save file", self.current_file_path or "untitled.txt",
            "Text Files (*.txt);;All Files (*)"
        )
        if not path:
            return

        self.current_file_path = path
        self._write_to(path)

    def _write_to(self, path):
        try:
            Path(path).write_text(self.text_edit.toPlainText(), encoding="utf-8")
        except OSError as error:
            self.title_label.setText(f"Notepad — failed to save: {error}")
            return

        self._update_title()

    def _update_title(self):
        name = os.path.basename(self.current_file_path) if self.current_file_path else "untitled"
        self.title_label.setText(f"Notepad — {name}")

    # ------------------------------------------------------------------
    # Show/hide
    # ------------------------------------------------------------------

    def show_window(self):
        if not self._positioned:
            screen = QApplication.primaryScreen().availableGeometry()
            self.move(screen.center().x() - self.width() // 2, screen.center().y() - self.height() // 2)
            self._positioned = True

        self.show()
        self.raise_()
        self.activateWindow()
        self.text_edit.setFocus()

    def hide_window(self):
        self.hide()

    def toggle(self):
        if self.isVisible():
            self.hide_window()
        else:
            self.show_window()

    # ------------------------------------------------------------------
    # Theming
    # ------------------------------------------------------------------

    def _apply_style(self):
        self.setStyleSheet(f"""
            DraggableFrame {{
                background-color: {Theme.BG_DARK};
                border: 1px solid {Theme.PINK};
                border-radius: 14px;
                color: white;
                font-family: "{self.font_family}";
            }}
        """)

        self._icon_label.setPixmap(qta.icon("fa5s.sticky-note", color=Theme.PINK).pixmap(QSize(16, 16)))

        for button in (self.new_button, self.open_button, self.save_button, self.close_button):
            icon_name = button.property("icon_name")
            button.setIcon(qta.icon(icon_name, color=Theme.PINK_SOFT, color_active="white"))
            button.setStyleSheet(f"""
                QPushButton {{
                    background-color: #16051a;
                    border: 1px solid {Theme.PINK};
                    border-radius: 8px;
                    color: {Theme.PINK_SOFT};
                }}
                QPushButton:hover {{
                    background-color: {Theme.PINK};
                    color: white;
                }}
            """)

        self.text_edit.setStyleSheet(f"""
            QTextEdit {{
                background-color: {Theme.BG_BUBBLE};
                color: white;
                border: 1px solid {Theme.PINK};
                border-radius: 8px;
                padding: 10px;
                font-size: 13px;
            }}
        """)