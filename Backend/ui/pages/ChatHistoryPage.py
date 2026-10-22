from PyQt6.QtCore import Qt, pyqtSignal, QEvent
from PyQt6.QtGui import QColor, QPainter, QLinearGradient
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea, QFrame

from ai.ChatHistory import chat_history
from ui.utils.ImageUtils import pil_to_qpixmap
from ui.componenets.MessageComposer import MessageComposer
import ui.utils.Theme as Theme
from ui.utils.Typography import FONT_SIZE_XS, FONT_SIZE_LG
from ui.utils.Shapes import (
    RADIUS_LG,
    RADIUS_XL,
    BORDER_NONE,
    BORDER_MEDIUM,
    SCROLLBAR_WIDTH_THIN,
    INPUT_BAR_MIN_HEIGHT,
)
from ui.utils.Spacing import (
    SPACE_0,
    SPACE_SM,
    SPACE_MD,
    SPACE_LG,
    LAYOUT_SPACING_LOOSE,
)

THUMBNAIL_MAX_SIZE = (200, 150)

CHAT_BG_COLOR = "#080108"
TOP_FADE_HEIGHT = 80


class FadeOverlay(QWidget):
    """Gradient that goes from opaque (top) to transparent (bottom).

    Placed over the scroll area's viewport so messages appear to fade out
    as they scroll up. Ignores mouse events so scrolling and text selection
    keep working underneath it.
    """

    def __init__(self, parent, color=CHAT_BG_COLOR, height=TOP_FADE_HEIGHT):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setFixedHeight(height)
        self._color = QColor(color)

    def set_color(self, color):
        self._color = QColor(color)
        self.update()

    def paintEvent(self, event):
        opaque = QColor(self._color)
        opaque.setAlpha(255)
        mid = QColor(self._color)
        mid.setAlpha(120)
        clear = QColor(self._color)
        clear.setAlpha(0)  # same RGB, so no gray fringing

        gradient = QLinearGradient(0, 0, 0, self.height())
        gradient.setColorAt(0.0, opaque)
        gradient.setColorAt(0.5, mid)
        gradient.setColorAt(1.0, clear)

        painter = QPainter(self)
        painter.fillRect(self.rect(), gradient)


class ChatBubble(QFrame):
    def __init__(self, text, timestamp, side="left", image=None):
        super().__init__()

        column = QVBoxLayout()
        column.setSpacing(SPACE_SM)

        if image is not None:
            thumbnail_label = QLabel()
            pixmap = pil_to_qpixmap(image).scaled(
                THUMBNAIL_MAX_SIZE[0], THUMBNAIL_MAX_SIZE[1],
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            thumbnail_label.setPixmap(pixmap)

            column.addWidget(
                thumbnail_label,
                alignment=Qt.AlignmentFlag.AlignRight if side == "right" else Qt.AlignmentFlag.AlignLeft,
            )

        self._text_bubble = None
        if text:
            self._text_bubble = QLabel(text)
            self._text_bubble.setWordWrap(True)
            column.addWidget(self._text_bubble)

        self._time_label = QLabel(timestamp)
        column.addWidget(
            self._time_label,
            alignment=Qt.AlignmentFlag.AlignRight if side == "right" else Qt.AlignmentFlag.AlignLeft,
        )

        row = QHBoxLayout(self)
        row.setContentsMargins(SPACE_0, SPACE_0, SPACE_0, SPACE_0)

        if side == "left":
            row.addLayout(column)
            row.addStretch()
        else:
            row.addStretch()
            row.addLayout(column)

        self._apply_style()
        Theme.theme_signals.changed.connect(self._apply_style)

    def _apply_style(self):
        if self._text_bubble is not None:
            self._text_bubble.setStyleSheet(f"""
                QLabel {{
                    background-color: {Theme.BG_ELEVATED};
                    color: white;
                    padding: {SPACE_MD}px {SPACE_LG}px;
                    border-radius: {RADIUS_LG}px;
                    font-size: {FONT_SIZE_LG}px;
                }}
            """)
        self._time_label.setStyleSheet(f"color: {Theme.ACCENT_SOFT}; font-size: {FONT_SIZE_XS}px;")


class ChatHistoryPage(QWidget):
    message_added = pyqtSignal(dict)

    def __init__(self, process_question):
        super().__init__()
        self.process_question = process_question

        layout = QVBoxLayout(self)
        layout.setContentsMargins(SPACE_0, SPACE_0, SPACE_0, SPACE_0)
        layout.setSpacing(LAYOUT_SPACING_LOOSE)

        layout.addWidget(self._build_chat_area(), stretch=1)
        layout.addWidget(self._build_input_bar())

        self.message_added.connect(self._append_message)

        # Carrega histórico existente e assina novos eventos
        for message in chat_history.get_all():
            self._append_message(message)

        chat_history.subscribe(lambda message: self.message_added.emit(message))

        Theme.theme_signals.changed.connect(self._apply_input_bar_style)

    def _build_chat_area(self):
        self.chat_scroll = QScrollArea()
        self.chat_scroll.setWidgetResizable(True)
        self.chat_scroll.setStyleSheet(f"""
            QScrollArea {{
                background-color: {CHAT_BG_COLOR};
                border: {BORDER_NONE}px;
            }}
            QScrollArea > QWidget > QWidget {{
                background-color: {CHAT_BG_COLOR};
            }}

            /* Fundo da barra de rolagem */
            QScrollBar:vertical {{
                background-color: {Theme.BG_ELEVATED};
                width: {SCROLLBAR_WIDTH_THIN}px;
                margin: 0px;
                border: none;
            }}
        """)

        content = QWidget()
        self.messages_layout = QVBoxLayout(content)
        self.messages_layout.setSpacing(LAYOUT_SPACING_LOOSE)
        self.messages_layout.setContentsMargins(SPACE_MD, SPACE_MD, SPACE_MD, SPACE_MD)
        self.messages_layout.addStretch()

        self.chat_scroll.setWidget(content)

        # rangeChanged fires exactly when the scrollable content height changes
        # (e.g. right after a new bubble is inserted), so it's a more reliable
        # trigger than a singleShot(0) call placed right after insertWidget.
        self.chat_scroll.verticalScrollBar().rangeChanged.connect(
            lambda _min, _max: self._scroll_to_bottom()
        )

        # Fade overlay on top of the viewport: messages dissolve into the
        # background as they scroll up.
        viewport = self.chat_scroll.viewport()
        self._top_fade = FadeOverlay(viewport, color=CHAT_BG_COLOR, height=TOP_FADE_HEIGHT)
        self._top_fade.setGeometry(0, 0, viewport.width(), TOP_FADE_HEIGHT)
        self._top_fade.raise_()
        viewport.installEventFilter(self)

        return self.chat_scroll

    def eventFilter(self, obj, event):
        if obj is self.chat_scroll.viewport() and event.type() == QEvent.Type.Resize:
            self._top_fade.setGeometry(0, 0, obj.width(), self._top_fade.height())
            self._top_fade.raise_()
        return super().eventFilter(obj, event)

    def _build_input_bar(self):
        self._input_bar = QFrame()
        self._input_bar.setMinimumHeight(INPUT_BAR_MIN_HEIGHT)

        layout = QHBoxLayout(self._input_bar)
        layout.setContentsMargins(SPACE_LG, SPACE_MD, SPACE_LG, SPACE_MD)

        self.composer = MessageComposer(
            self.process_question, compact=True, placeholder="Type a message..."
        )
        layout.addWidget(self.composer)

        self._apply_input_bar_style()

        return self._input_bar

    def _apply_input_bar_style(self):
        self._input_bar.setStyleSheet(f"""
            QFrame {{
                background-color: #16051a;
                border: {BORDER_MEDIUM}px solid {Theme.ACCENT};
                border-radius: {RADIUS_XL}px;
            }}
        """)

    def _append_message(self, message):
        side = "right" if message["role"] == "user" else "left"
        bubble = ChatBubble(
            message["text"], message["timestamp"],
            side=side, image=message.get("image"),
        )

        self.messages_layout.addWidget(bubble)
        # rangeChanged (connected in _build_chat_area) now handles scrolling,
        # so the previous QTimer.singleShot(0, self._scroll_to_bottom) call
        # is no longer needed here.

    def _scroll_to_bottom(self):
        scrollbar = self.chat_scroll.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())