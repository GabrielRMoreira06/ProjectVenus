import qtawesome as qta
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea, QFrame

from ai.ChatHistory import chat_history
from ui.ImageUtils import pil_to_qpixmap
from ui.MessageComposer import MessageComposer
from ui.Theme import PINK, PINK_SOFT, BG_BUBBLE

THUMBNAIL_MAX_SIZE = (200, 150)


class ChatBubble(QFrame):
    def __init__(self, text, timestamp, side="left", image=None):
        super().__init__()

        column = QVBoxLayout()
        column.setSpacing(8)

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

        if text:
            bubble = QLabel(text)
            bubble.setWordWrap(True)
            bubble.setStyleSheet(f"""
                QLabel {{
                    background-color: {BG_BUBBLE};
                    color: white;
                    padding: 14px 18px;
                    border-radius: 12px;
                    font-size: 16px;
                }}
            """)
            column.addWidget(bubble)

        time_label = QLabel(timestamp)
        time_label.setStyleSheet(f"color: {PINK_SOFT}; font-size: 11px;")
        column.addWidget(
            time_label,
            alignment=Qt.AlignmentFlag.AlignRight if side == "right" else Qt.AlignmentFlag.AlignLeft,
        )

        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)

        if side == "left":
            row.addLayout(column)
            row.addStretch()
        else:
            row.addStretch()
            row.addLayout(column)


class ChatHistoryPage(QWidget):
    message_added = pyqtSignal(dict)

    def __init__(self, process_question):
        super().__init__()
        self.process_question = process_question

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)

        layout.addWidget(self._build_chat_area(), stretch=1)
        layout.addWidget(self._build_input_bar())

        self.message_added.connect(self._append_message)

        # Carrega histórico existente e assina novos eventos
        for message in chat_history.get_all():
            self._append_message(message)

        chat_history.subscribe(lambda message: self.message_added.emit(message))

    def _build_chat_area(self):
        self.chat_scroll = QScrollArea()
        self.chat_scroll.setWidgetResizable(True)
        self.chat_scroll.setStyleSheet(f"""
            QScrollArea {{
                background-color: #080108;
                border: none;
            }}
            QScrollArea > QWidget > QWidget {{
                background-color: #080108;
            }}
        """)

        content = QWidget()
        self.messages_layout = QVBoxLayout(content)
        self.messages_layout.setSpacing(14)
        self.messages_layout.setContentsMargins(12, 12, 12, 12)
        self.messages_layout.addStretch()

        self.chat_scroll.setWidget(content)
        return self.chat_scroll

    def _build_input_bar(self):
        bar = QFrame()
        bar.setStyleSheet(f"""
            QFrame {{
                background-color: #16051a;
                border: 2px solid {PINK};
                border-radius: 16px;
            }}
        """)
        bar.setMinimumHeight(64)

        layout = QHBoxLayout(bar)
        layout.setContentsMargins(14, 10, 14, 10)

        self.composer = MessageComposer(
            self.process_question, compact=True, placeholder="Type a message..."
        )
        layout.addWidget(self.composer)

        return bar

    def _append_message(self, message):
        side = "right" if message["role"] == "user" else "left"
        bubble = ChatBubble(
            message["text"], message["timestamp"],
            side=side, image=message.get("image"),
        )

        insert_index = self.messages_layout.count() - 1
        self.messages_layout.insertWidget(insert_index, bubble)

        QTimer.singleShot(0, self._scroll_to_bottom)

    def _scroll_to_bottom(self):
        scrollbar = self.chat_scroll.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())