"""
MemoriesPage.py

Tools > Memories. Browses everything Venus has stored in memory.json
(memories, facts, daily summaries) with edit/delete per entry. Reads
and writes through the SAME MemoryManager instance GeminiWorker owns
(worker.memory), and refreshes live whenever it changes.
"""

import qtawesome as qta
from PyQt6.QtCore import Qt, QSize, pyqtSignal
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame,
    QScrollArea, QInputDialog, QMessageBox,
)

from ai.core.GeminiWorker import worker
import ui.utils.Theme as Theme
from ui.utils.Typography import (
    FONT_SIZE_SM, FONT_SIZE_MD, FONT_SIZE_LG, FONT_SIZE_XXL, FONT_WEIGHT_BOLD,
)
from ui.utils.Shapes import (
    RADIUS_SM, RADIUS_MD, RADIUS_LG, RADIUS_PILL, BORDER_THIN,
    ICON_SIZE_SM, ICON_SIZE_LG, ICON_SIZE_XL, BUTTON_HEIGHT_LG, BUTTON_HEIGHT_XL,
)
from ui.utils.Spacing import SPACE_0, SPACE_XS, SPACE_SM, SPACE_MD, SPACE_LG, LAYOUT_SPACING_LOOSE

TABS = [
    ("memories", "Memories"),
    ("facts", "Facts"),
    ("daily_summaries", "Daily Summaries"),
]

ROW_BUTTON_WIDTH = 96
SPACE_XL_PAD = 20
DATE_LABEL_WIDTH = 100


def _split_text(text):
    text = text.strip()

    if "\n" in text:
        title, detail = text.split("\n", 1)
        return title.strip(), detail.strip()

    head, sep, tail = text.partition(". ")
    if sep and tail.strip():
        return head + ".", tail.strip()

    return text, ""


class _CountBadge(QLabel):

    def __init__(self, count=0):
        super().__init__(str(count))
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMinimumWidth(28)
        self.setFixedHeight(24)

    def set_count(self, count):
        self.setText(str(count))


class _TabButton(QPushButton):

    def __init__(self, label, count=0, active=False):
        super().__init__()
        self._active = active
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(BUTTON_HEIGHT_XL + SPACE_SM)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(SPACE_LG, SPACE_0, SPACE_LG, SPACE_0)
        layout.setSpacing(SPACE_MD)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._text = QLabel(label)
        self._badge = _CountBadge(count)
        for widget in (self._text, self._badge):
            widget.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            layout.addWidget(widget)

        self._apply_style()
        Theme.theme_signals.changed.connect(self._apply_style)

    def set_active(self, active):
        self._active = active
        self._apply_style()

    def set_count(self, count):
        self._badge.set_count(count)

    def _apply_style(self):
        if self._active:
            self.setStyleSheet(f"""
                QPushButton {{
                    background-color: {Theme.ACCENT};
                    border: {BORDER_THIN}px solid {Theme.ACCENT};
                    border-radius: {RADIUS_SM}px;
                }}
            """)
            text_color = "white"
        else:
            self.setStyleSheet(f"""
                QPushButton {{
                    background-color: transparent;
                    border: {BORDER_THIN}px solid {Theme.ACCENT};
                    border-radius: {RADIUS_SM}px;
                }}
                QPushButton:hover {{ background-color: {Theme.BG_ELEVATED}; }}
            """)
            text_color = Theme.ACCENT_SOFT

        self._text.setStyleSheet(
            f"color: {text_color}; font-size: {FONT_SIZE_LG}px; border: none; background: transparent;")
        self._badge.setStyleSheet(f"""
            background-color: #2a0a33;
            color: {Theme.ACCENT if self._active else "white"};
            font-size: {FONT_SIZE_SM}px;
            border: none;
            border-radius: {RADIUS_PILL}px;
            padding: 0px {SPACE_SM}px;
        """)


class MemoryRow(QFrame):

    edit_requested = pyqtSignal(str)
    delete_requested = pyqtSignal(str)

    def __init__(self, entry_id, text, date):
        super().__init__()
        self.setObjectName("memoryRow")
        self.entry_id = entry_id
        self.text = text

        title, detail = _split_text(text)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(SPACE_LG, SPACE_MD, SPACE_LG, SPACE_MD)
        layout.setSpacing(SPACE_LG)

        text_column = QVBoxLayout()
        text_column.setSpacing(SPACE_XS)

        self.title_label = QLabel(title)
        self.title_label.setWordWrap(True)
        text_column.addWidget(self.title_label)

        self.detail_label = QLabel(detail)
        self.detail_label.setWordWrap(True)
        self.detail_label.setVisible(bool(detail))
        text_column.addWidget(self.detail_label)

        layout.addLayout(text_column, stretch=1)

        self.date_label = QLabel(date.strftime("%b %d, %Y") if date else "—")
        self.date_label.setFixedWidth(DATE_LABEL_WIDTH)
        self.date_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.date_label)

        self.edit_button = self._make_button("Edit", "fa5s.pencil-alt")
        self.edit_button.clicked.connect(lambda: self.edit_requested.emit(self.entry_id))
        layout.addWidget(self.edit_button)

        self.delete_button = self._make_button("Delete", "fa5s.trash-alt")
        self.delete_button.clicked.connect(lambda: self.delete_requested.emit(self.entry_id))
        layout.addWidget(self.delete_button)

        self._apply_style()
        Theme.theme_signals.changed.connect(self._apply_style)

    def _make_button(self, label, icon_name):
        button = QPushButton(f" {label}")
        button.setProperty("icon_name", icon_name)
        button.setFixedSize(ROW_BUTTON_WIDTH, BUTTON_HEIGHT_LG)
        button.setIconSize(QSize(ICON_SIZE_SM, ICON_SIZE_SM))
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        return button

    def _apply_style(self):
        self.setStyleSheet(f"""
            #memoryRow {{
                background-color: #18051b;
                border: {BORDER_THIN}px solid #2a0a33;
                border-radius: {RADIUS_LG}px;
            }}
        """)
        self.title_label.setStyleSheet(
            f"color: white; font-size: {FONT_SIZE_LG}px; border: none; background: transparent;")
        self.detail_label.setStyleSheet(
            f"color: {Theme.ACCENT_SOFT}; font-size: {FONT_SIZE_SM}px; border: none; background: transparent;")
        self.date_label.setStyleSheet(
            f"color: {Theme.ACCENT}; font-size: {FONT_SIZE_SM}px; border: none; background: transparent;")

        for button in (self.edit_button, self.delete_button):
            button.setIcon(qta.icon(button.property("icon_name"), color=Theme.ACCENT, color_active="white"))
            button.setStyleSheet(f"""
                QPushButton {{
                    background-color: transparent;
                    border: {BORDER_THIN}px solid {Theme.ACCENT};
                    border-radius: {RADIUS_SM}px;
                    color: white;
                    font-size: {FONT_SIZE_SM}px;
                }}
                QPushButton:hover {{ background-color: {Theme.BG_ELEVATED}; }}
            """)


class MemoriesPage(QWidget):

    refresh_requested = pyqtSignal()

    def __init__(self, memory=None):
        super().__init__()
        self.memory = memory or worker.memory
        self._category = TABS[0][0]

        outer = QVBoxLayout(self)
        outer.setContentsMargins(SPACE_0, SPACE_0, SPACE_0, SPACE_0)
        outer.setSpacing(LAYOUT_SPACING_LOOSE)

        outer.addLayout(self._build_header())
        outer.addLayout(self._build_tabs())

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        content = QWidget()
        content.setStyleSheet("background: transparent;")
        self._list_layout = QVBoxLayout(content)
        self._list_layout.setContentsMargins(SPACE_0, SPACE_0, SPACE_0, SPACE_0)
        self._list_layout.setSpacing(SPACE_MD)
        self._scroll.setWidget(content)
        outer.addWidget(self._scroll, stretch=1)

        self._apply_style()
        Theme.theme_signals.changed.connect(self._apply_style)

        self.refresh_requested.connect(self.refresh)
        self.memory.subscribe(self.refresh_requested.emit)

        self.refresh()

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------

    def _build_header(self):
        header = QHBoxLayout()
        header.setSpacing(SPACE_MD)

        self._header_icon = QLabel()
        self._header_icon.setFixedSize(ICON_SIZE_XL + SPACE_XL_PAD, ICON_SIZE_XL + SPACE_XL_PAD)
        self._header_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._header_title = QLabel("Memories")
        self._total_badge = _CountBadge(0)
        self._total_badge.setFixedHeight(32)
        self._total_badge.setMinimumWidth(44)

        header.addWidget(self._header_icon)
        header.addWidget(self._header_title)
        header.addWidget(self._total_badge)
        header.addStretch()
        return header

    def _build_tabs(self):
        row = QHBoxLayout()
        row.setSpacing(SPACE_0)

        self._tab_buttons = {}
        for category, label in TABS:
            button = _TabButton(label, active=(category == self._category))
            button.clicked.connect(lambda _checked=False, c=category: self._switch_tab(c))
            self._tab_buttons[category] = button
            row.addWidget(button, stretch=1)

        return row

    # ------------------------------------------------------------------
    # Behavior
    # ------------------------------------------------------------------

    def _switch_tab(self, category):
        self._category = category
        for key, button in self._tab_buttons.items():
            button.set_active(key == category)
        self.refresh()

    def refresh(self):
        counts = self.memory.counts()
        self._total_badge.set_count(sum(counts.values()))
        for category, button in self._tab_buttons.items():
            button.set_count(counts.get(category, 0))

        while self._list_layout.count():
            item = self._list_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        entries = self.memory.list_entries(self._category)

        if not entries:
            empty = QLabel("Nothing here yet")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty.setStyleSheet(
                f"color: {Theme.ACCENT_SOFT}; font-size: {FONT_SIZE_MD}px; border: none; background: transparent;")
            self._list_layout.addWidget(empty)
            self._list_layout.addStretch()
            return

        for entry in entries:
            row = MemoryRow(entry["id"], entry["text"], entry["date"])
            row.edit_requested.connect(lambda entry_id, r=row: self._edit(entry_id, r.text))
            row.delete_requested.connect(self._delete)
            self._list_layout.addWidget(row)

        self._list_layout.addStretch()

    def _edit(self, entry_id, current_text):
        text, accepted = QInputDialog.getMultiLineText(self, "Edit entry", "Text:", current_text)

        if not accepted or not text.strip() or text.strip() == current_text.strip():
            return

        self.memory.update_entry(self._category, entry_id, text)

    def _delete(self, entry_id):
        answer = QMessageBox.question(self, "Delete entry", "Delete this entry from Venus's memory?")

        if answer != QMessageBox.StandardButton.Yes:
            return

        self.memory.delete_entry(self._category, entry_id)

    # ------------------------------------------------------------------
    # Theming
    # ------------------------------------------------------------------

    def _apply_style(self):
        self._header_icon.setPixmap(
            qta.icon("fa5s.images", color="white").pixmap(QSize(ICON_SIZE_LG + 4, ICON_SIZE_LG + 4)))
        self._header_icon.setStyleSheet(
            f"background-color: {Theme.ACCENT}; border: none; border-radius: {RADIUS_MD}px;")
        self._header_title.setStyleSheet(
            f"color: {Theme.ACCENT}; font-size: {FONT_SIZE_XXL}px; font-weight: {FONT_WEIGHT_BOLD}; "
            "border: none; background: transparent;")
        self._total_badge.setStyleSheet(f"""
            background-color: #2a0a33;
            color: white;
            font-size: {FONT_SIZE_MD}px;
            border: none;
            border-radius: {RADIUS_PILL}px;
            padding: 0px {SPACE_MD}px;
        """)