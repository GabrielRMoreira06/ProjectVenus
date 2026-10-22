import os
from pathlib import Path

import qtawesome as qta
from PyQt6.QtCore import Qt, QSize, QRect, QPoint, QObject, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QKeySequence, QPainter, QShortcut
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame,
    QPlainTextEdit, QFileDialog, QMenu, QMessageBox,
)

from config import NOTEPAD_PATH as AUTOSAVE_PATH
import ui.utils.Theme as Theme
from ui.utils.Typography import FONT_SIZE_SM, FONT_SIZE_MD, FONT_SIZE_XXL, FONT_WEIGHT_BOLD
from ui.utils.Shapes import (
    RADIUS_SM, RADIUS_MD, RADIUS_LG, BORDER_THIN, BORDER_MEDIUM,
    ICON_SIZE_SM, ICON_SIZE_MD, ICON_SIZE_XL, BUTTON_HEIGHT_MD,
)
from ui.utils.Spacing import SPACE_0, SPACE_XS, SPACE_SM, SPACE_MD, SPACE_LG, LAYOUT_SPACING_LOOSE

AUTOSAVE_DEBOUNCE_MS = 1000
DEFAULT_FILE_NAME = "notes.txt"
EDITOR_FONT_FAMILY = "Consolas"
EDITOR_FONT_SIZE = 13
GUTTER_PADDING = 14
TOOL_BUTTON_WIDTH = 56


class _NotepadSignals(QObject):
    content_changed = pyqtSignal(str)


notepad_signals = _NotepadSignals()


def _dim_pink(alpha=90):
    color = QColor(Theme.ACCENT)
    return f"rgba({color.red()}, {color.green()}, {color.blue()}, {alpha})"


class _LineNumberArea(QWidget):
    def __init__(self, editor):
        super().__init__(editor)
        self.editor = editor

    def sizeHint(self):
        return QSize(self.editor.gutter_width(), 0)

    def paintEvent(self, event):
        self.editor.paint_gutter(event)


class _CodeEditor(QPlainTextEdit):
    def __init__(self):
        super().__init__()
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.setFont(QFont(EDITOR_FONT_FAMILY, 11))
        self.setTabStopDistance(self.fontMetrics().horizontalAdvance(" ") * 4)

        self._gutter = _LineNumberArea(self)

        self.blockCountChanged.connect(self._update_gutter_width)
        self.updateRequest.connect(self._update_gutter)
        self.cursorPositionChanged.connect(self._gutter.update)
        self._update_gutter_width()

    def gutter_width(self):
        digits = max(2, len(str(max(1, self.blockCount()))))
        return GUTTER_PADDING * 2 + self.fontMetrics().horizontalAdvance("9") * digits

    def _update_gutter_width(self, *_args):
        self.setViewportMargins(self.gutter_width(), 0, 0, 0)

    def _update_gutter(self, rect, dy):
        if dy:
            self._gutter.scroll(0, dy)
        else:
            self._gutter.update(0, rect.y(), self._gutter.width(), rect.height())

        if rect.contains(self.viewport().rect()):
            self._update_gutter_width()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        area = self.contentsRect()
        self._gutter.setGeometry(QRect(area.left(), area.top(), self.gutter_width(), area.height()))

    def paint_gutter(self, event):
        painter = QPainter(self._gutter)
        width = self._gutter.width()

        painter.setPen(QColor(Theme.ACCENT).darker(300))
        painter.drawLine(width - 1, event.rect().top(), width - 1, event.rect().bottom())

        dim = QColor(Theme.ACCENT_SOFT)
        dim.setAlpha(150)
        current_line = self.textCursor().blockNumber()

        block = self.firstVisibleBlock()
        number = block.blockNumber()
        top = round(self.blockBoundingGeometry(block).translated(self.contentOffset()).top())
        bottom = top + round(self.blockBoundingRect(block).height())

        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                painter.setPen(QColor("white") if number == current_line else dim)
                painter.drawText(
                    0, top, width - GUTTER_PADDING, self.fontMetrics().height(),
                    Qt.AlignmentFlag.AlignRight, str(number + 1),
                )

            block = block.next()
            top = bottom
            bottom = top + round(self.blockBoundingRect(block).height())
            number += 1

        painter.end()


class NotepadPage(QWidget):

    def __init__(self):
        super().__init__()

        self.current_file_path = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(SPACE_0, SPACE_0, SPACE_0, SPACE_0)
        outer.setSpacing(LAYOUT_SPACING_LOOSE)

        outer.addLayout(self._build_header())
        outer.addWidget(self._build_card(), stretch=1)

        self._autosave_timer = QTimer(self)
        self._autosave_timer.setSingleShot(True)
        self._autosave_timer.timeout.connect(self._write_autosave)
        self.editor.textChanged.connect(self._schedule_autosave)
        self.editor.cursorPositionChanged.connect(self._update_cursor_label)

        self._load_autosave()
        self._update_cursor_label()
        notepad_signals.content_changed.connect(self._on_external_content_changed)

        QShortcut(QKeySequence("Ctrl+S"), self, activated=self.save_file,
                  context=Qt.ShortcutContext.WidgetWithChildrenShortcut)
        QShortcut(QKeySequence("Ctrl+O"), self, activated=self.open_file,
                  context=Qt.ShortcutContext.WidgetWithChildrenShortcut)

        self._apply_style()
        Theme.theme_signals.changed.connect(self._apply_style)

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------

    def _build_header(self):
        header = QHBoxLayout()
        header.setSpacing(SPACE_MD)

        self._header_icon = QLabel()
        self._header_title = QLabel("Notepad")

        header.addWidget(self._header_icon)
        header.addWidget(self._header_title)
        header.addStretch()
        return header

    def _build_card(self):
        self._card = QFrame()
        self._card.setObjectName("notepadCard")

        layout = QVBoxLayout(self._card)
        layout.setContentsMargins(SPACE_0, SPACE_0, SPACE_0, SPACE_0)
        layout.setSpacing(SPACE_0)

        layout.addWidget(self._build_toolbar())

        self.editor = _CodeEditor()
        layout.addWidget(self.editor, stretch=1)

        layout.addWidget(self._build_footer())
        return self._card

    def _build_toolbar(self):
        self._toolbar = QFrame()
        self._toolbar.setObjectName("notepadToolbar")

        layout = QHBoxLayout(self._toolbar)
        layout.setContentsMargins(SPACE_LG, SPACE_0, SPACE_0, SPACE_0)
        layout.setSpacing(SPACE_0)

        self.name_button = QPushButton()
        self.name_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.name_button.setFixedHeight(BUTTON_HEIGHT_MD + SPACE_LG)
        self.name_button.clicked.connect(self._open_name_menu)

        name_layout = QHBoxLayout(self.name_button)
        name_layout.setContentsMargins(SPACE_0, SPACE_0, SPACE_0, SPACE_0)
        name_layout.setSpacing(SPACE_MD)

        self._file_icon = QLabel()
        self.name_label = QLabel(DEFAULT_FILE_NAME)
        self._name_chevron = QLabel()
        for label in (self._file_icon, self.name_label, self._name_chevron):
            label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            name_layout.addWidget(label)

        layout.addWidget(self.name_button)
        layout.addStretch()

        self.save_button = self._make_tool_button(self.save_file)
        self.open_button = self._make_tool_button(self.open_file)
        self.clear_button = self._make_tool_button(self.clear_notepad)
        self._tool_buttons = [
            (self.save_button, "fa5.save"),
            (self.open_button, "fa5.folder-open"),
            (self.clear_button, "fa5.trash-alt"),
        ]

        for button, _icon in self._tool_buttons:
            layout.addWidget(button)

        return self._toolbar

    def _make_tool_button(self, on_click):
        button = QPushButton()
        button.setFixedSize(TOOL_BUTTON_WIDTH, BUTTON_HEIGHT_MD + SPACE_LG)
        button.setIconSize(QSize(ICON_SIZE_MD + 4, ICON_SIZE_MD + 4))
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.clicked.connect(on_click)
        return button

    def _build_footer(self):
        self._footer = QFrame()
        self._footer.setObjectName("notepadFooter")

        layout = QHBoxLayout(self._footer)
        layout.setContentsMargins(SPACE_LG, SPACE_SM, SPACE_LG, SPACE_SM)

        self.cursor_label = QLabel("Ln 1, Col 1")
        layout.addWidget(self.cursor_label)
        layout.addStretch()

        self.mode_button = QPushButton("Plain Text")
        self.mode_button.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.mode_button.setIconSize(QSize(ICON_SIZE_SM - 4, ICON_SIZE_SM - 4))
        self.mode_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.mode_button.clicked.connect(self._open_mode_menu)
        layout.addWidget(self.mode_button)

        return self._footer

    # ------------------------------------------------------------------
    # Menus
    # ------------------------------------------------------------------

    def _styled_menu(self):
        menu = QMenu(self)
        menu.setStyleSheet(f"""
            QMenu {{
                background-color: {Theme.BG_SURFACE};
                color: white;
                border: {BORDER_THIN}px solid {Theme.ACCENT};
                border-radius: {RADIUS_SM}px;
                padding: {SPACE_XS}px;
            }}
            QMenu::item {{
                padding: {SPACE_SM}px {SPACE_LG}px;
                border-radius: {RADIUS_SM}px;
            }}
            QMenu::item:selected {{ background-color: {Theme.ACCENT}; }}
        """)
        return menu

    def _open_name_menu(self):
        menu = self._styled_menu()
        menu.addAction("New", self.new_file)
        menu.addAction("Open...", self.open_file)
        menu.addAction("Save As...", self.save_file_as)
        menu.exec(self.name_button.mapToGlobal(self.name_button.rect().bottomLeft()))

    def _open_mode_menu(self):
        menu = self._styled_menu()
        action = menu.addAction("Plain Text")
        action.setCheckable(True)
        action.setChecked(True)
        anchor = self.mode_button.mapToGlobal(self.mode_button.rect().topLeft())
        menu.exec(QPoint(anchor.x(), anchor.y() - menu.sizeHint().height()))

    # ------------------------------------------------------------------
    # Autosave (independent of New/Open/Save/Save As)
    # ------------------------------------------------------------------

    def _load_autosave(self):
        if not AUTOSAVE_PATH.exists():
            return

        try:
            content = AUTOSAVE_PATH.read_text(encoding="utf-8")
        except OSError:
            return

        self.editor.setPlainText(content)

    def _schedule_autosave(self):
        self._autosave_timer.start(AUTOSAVE_DEBOUNCE_MS)

    def _write_autosave(self):
        try:
            AUTOSAVE_PATH.write_text(self.editor.toPlainText(), encoding="utf-8")
        except OSError:
            pass

    def _on_external_content_changed(self, content):
        self.editor.setPlainText(content)

    def hideEvent(self, event):
        if self._autosave_timer.isActive():
            self._autosave_timer.stop()
            self._write_autosave()

        super().hideEvent(event)

    # ------------------------------------------------------------------
    # File operations
    # ------------------------------------------------------------------

    def new_file(self):
        self.editor.clear()
        self.current_file_path = None
        self._update_name()

    def open_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Open file", "", "Text Files (*.txt);;All Files (*)"
        )
        if not path:
            return

        try:
            content = Path(path).read_text(encoding="utf-8")
        except OSError as error:
            QMessageBox.warning(self, "Notepad", f"Failed to open file:\n{error}")
            return

        self.editor.setPlainText(content)
        self.current_file_path = path
        self._update_name()

    def save_file(self):
        if self.current_file_path is None:
            self.save_file_as()
            return

        self._write_to(self.current_file_path)

    def save_file_as(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Save file", self.current_file_path or DEFAULT_FILE_NAME,
            "Text Files (*.txt);;All Files (*)"
        )
        if not path:
            return

        self.current_file_path = path
        self._write_to(path)

    def clear_notepad(self):
        if not self.editor.toPlainText():
            return

        answer = QMessageBox.question(
            self, "Clear notepad", "Clear everything in the notepad?"
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        self.editor.clear()

    def _write_to(self, path):
        try:
            Path(path).write_text(self.editor.toPlainText(), encoding="utf-8")
        except OSError as error:
            QMessageBox.warning(self, "Notepad", f"Failed to save file:\n{error}")
            return

        self._update_name()

    def _update_name(self):
        name = os.path.basename(self.current_file_path) if self.current_file_path else DEFAULT_FILE_NAME
        self.name_label.setText(name)

    def _update_cursor_label(self):
        cursor = self.editor.textCursor()
        self.cursor_label.setText(f"Ln {cursor.blockNumber() + 1}, Col {cursor.positionInBlock() + 1}")

    # ------------------------------------------------------------------
    # Theming
    # ------------------------------------------------------------------

    def _apply_style(self):
        divider = _dim_pink(90)

        self._header_icon.setPixmap(
            qta.icon("fa5s.file-alt", color=Theme.ACCENT).pixmap(QSize(ICON_SIZE_XL, ICON_SIZE_XL)))
        self._header_icon.setStyleSheet("border: none; background: transparent;")
        self._header_title.setStyleSheet(
            f"color: {Theme.ACCENT}; font-size: {FONT_SIZE_XXL}px; font-weight: {FONT_WEIGHT_BOLD}; "
            "border: none; background: transparent;")

        self._card.setStyleSheet(f"""
            #notepadCard {{
                background-color: {Theme.BG_DARK};
                border: {BORDER_MEDIUM}px solid {Theme.ACCENT};
                border-radius: {RADIUS_LG}px;
            }}
        """)
        self._toolbar.setStyleSheet(f"""
            #notepadToolbar {{
                background: transparent;
                border: none;
                border-bottom: {BORDER_THIN}px solid {divider};
                border-radius: 0px;
            }}
        """)
        self._footer.setStyleSheet(f"""
            #notepadFooter {{
                background: transparent;
                border: none;
                border-top: {BORDER_THIN}px solid {divider};
                border-radius: 0px;
            }}
        """)

        self.name_button.setStyleSheet("QPushButton { background: transparent; border: none; }")
        self._file_icon.setPixmap(
            qta.icon("fa5.file", color=Theme.ACCENT).pixmap(QSize(ICON_SIZE_MD + 4, ICON_SIZE_MD + 4)))
        self._file_icon.setStyleSheet("border: none; background: transparent;")
        self.name_label.setStyleSheet(
            f"color: white; font-size: {FONT_SIZE_MD + 4}px; border: none; background: transparent;")
        self._name_chevron.setPixmap(
            qta.icon("fa5s.chevron-down", color=Theme.ACCENT_SOFT).pixmap(QSize(ICON_SIZE_SM - 4, ICON_SIZE_SM - 4)))
        self._name_chevron.setStyleSheet("border: none; background: transparent;")

        for button, icon_name in self._tool_buttons:
            button.setIcon(qta.icon(icon_name, color=Theme.ACCENT, color_active="white"))
            button.setStyleSheet(f"""
                QPushButton {{
                    background: transparent;
                    border: none;
                    border-left: {BORDER_THIN}px solid {divider};
                    border-radius: 0px;
                }}
                QPushButton:hover {{ background-color: {Theme.BG_ELEVATED}; }}
            """)

        self.editor.setStyleSheet(f"""
            QPlainTextEdit {{
                background: transparent;
                color: white;
                border: none;
                padding: {SPACE_SM}px {SPACE_SM}px;
                font-family: {EDITOR_FONT_FAMILY};
                font-size: {EDITOR_FONT_SIZE}px;
                selection-background-color: {Theme.ACCENT};
            }}
        """)
        self.editor.viewport().update()
        self.editor._gutter.update()

        self.cursor_label.setStyleSheet(
            f"color: {Theme.ACCENT_SOFT}; font-size: {FONT_SIZE_SM}px; border: none; background: transparent;")
        self.mode_button.setIcon(
            qta.icon("fa5s.chevron-down", color=Theme.ACCENT_SOFT))
        self.mode_button.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                border: none;
                color: {Theme.ACCENT_SOFT};
                font-size: {FONT_SIZE_SM}px;
            }}
            QPushButton:hover {{ color: white; }}
        """)