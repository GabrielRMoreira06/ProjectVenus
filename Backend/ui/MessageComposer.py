"""
MessageComposer.py

Reusable "type to Venus" widget: a pastable text box (Ctrl+V accepts
an image, same as text), an emoji picker, an attach-file button, and a
send button — all wired directly to process_question. Used in two
places:

  - TextInput.InputWindow: a small floating popup (compact=False),
    which hides itself once a message is sent (see send_started).
  - PanelWindow: a persistent chat bar at the bottom (compact=True),
    which stays open and just clears the field.

The composer owns all paste/attach/emoji/send/enable-disable behavior
so neither caller has to duplicate it. The only difference between the
two contexts is visual (compact swaps in a thinner, icon-based layout
with a transparent/borderless text field, meant to sit inside a
container that already supplies its own border — see PanelWindow) and
in what the CALLER does when send_started fires (InputWindow hides
itself; PanelWindow does nothing extra, since it's meant to stay
open). Emoji/attach buttons only exist in compact mode today — full
mode (the popup) never had them, so there's nothing to wire there yet.
"""

import threading
from pathlib import Path

from PIL import Image
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QImage
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QTextEdit, QPushButton, QLabel, QFileDialog,
)

from ui.ImageUtils import qimage_to_pil, pil_to_qpixmap
from ui.Theme import PINK, PINK_SOFT, BG_BUBBLE, BG_PANEL

# Curated set rather than a full OS emoji panel — Qt has no built-in
# emoji picker, and pulling in a native one is platform-specific for
# very little payoff over a fixed grid of the emojis actually likely
# to get used here.
EMOJI_CHOICES = [
    "😀", "😂", "😅", "😉", "😊", "😍",
    "😘", "😜", "🤔", "😏", "🙄", "😳",
    "😢", "😭", "😡", "😱", "😴", "🥱",
    "🤯", "🥳", "👍", "👎", "👏", "🙏",
    "💪", "🔥", "✨", "💯", "❤️", "💔",
]

IMAGE_FILE_FILTER = "Images (*.png *.jpg *.jpeg *.webp *.bmp *.gif)"


class PastableTextEdit(QTextEdit):
    """
    A normal QTextEdit, except:
    - Ctrl+V first checks whether the clipboard holds an IMAGE — if it
      does, it's emitted via a signal instead of being pasted as text
      (which would otherwise produce garbage or nothing at all).
    - Enter sends (emits send_requested) instead of inserting a
      newline; Shift+Enter still inserts one normally. Handled here,
      in keyPressEvent, rather than via QShortcut: QTextEdit consumes
      Key_Return itself in its own keyPressEvent, so a WidgetShortcut
      on Key_Return never reliably wins against it.
    """

    image_pasted = pyqtSignal(object)  # emits a PIL.Image
    send_requested = pyqtSignal()

    def insertFromMimeData(self, source):
        if source.hasImage():
            qimage = QImage(source.imageData())
            if not qimage.isNull():
                self.image_pasted.emit(qimage_to_pil(qimage))
                return
        super().insertFromMimeData(source)

    def keyPressEvent(self, event):
        is_return = event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter)
        shift_held = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)

        if is_return and not shift_held:
            self.send_requested.emit()
            return

        super().keyPressEvent(event)


class EmojiPicker(QWidget):
    """
    Small popup grid of emoji buttons, anchored below whatever button
    opened it. Qt.WindowType.Popup closes it automatically on any
    click outside — no manual dismiss logic needed.
    """

    emoji_selected = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent, Qt.WindowType.Popup)

        self.setStyleSheet(f"""
            QWidget {{
                background-color: {BG_PANEL};
                border: 1px solid {PINK};
                border-radius: 8px;
            }}
            QPushButton {{
                background: transparent;
                border: none;
                font-size: 18px;
            }}
            QPushButton:hover {{
                background-color: {BG_BUBBLE};
                border-radius: 4px;
            }}
        """)

        layout = QGridLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(4)

        columns = 6
        for index, emoji in enumerate(EMOJI_CHOICES):
            button = QPushButton(emoji)
            button.setFixedSize(32, 32)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(lambda _checked=False, e=emoji: self._select(e))
            layout.addWidget(button, index // columns, index % columns)

    def _select(self, emoji):
        self.emoji_selected.emit(emoji)
        self.close()


class MessageComposer(QWidget):

    send_started = pyqtSignal()   # fired the instant send() commits, before the network call
    send_finished = pyqtSignal()  # fired once process_question actually returns

    def __init__(self, process_question, compact=False, placeholder="Type a message..."):
        super().__init__()

        self.process_question = process_question
        self.compact = compact
        self.pending_image = None
        self.status_label = None  # only exists in full mode — see _build_full

        self.send_finished.connect(self._on_send_finished)

        if compact:
            self._build_compact(placeholder)
        else:
            self._build_full(placeholder)

    # ------------------------------------------------------------------
    # Layouts
    # ------------------------------------------------------------------

    def _build_compact(self, placeholder):
        """
        Thin icon-based bar for PanelWindow. The text field is
        transparent/borderless on purpose — PanelWindow wraps this in
        its own bordered QFrame, and a second nested border would look
        wrong.
        """
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(6)

        preview_row = QHBoxLayout()
        self.preview_label = QLabel()
        self.preview_label.setVisible(False)
        self.preview_label.setFixedHeight(60)

        self.remove_image_button = QPushButton("✕")
        self.remove_image_button.setVisible(False)
        self.remove_image_button.setFixedSize(22, 22)
        self.remove_image_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.remove_image_button.clicked.connect(self._remove_image)
        self.remove_image_button.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                border: 1px solid {PINK};
                border-radius: 11px;
                color: {PINK_SOFT};
            }}
            QPushButton:hover {{ color: white; }}
        """)

        preview_row.addWidget(self.preview_label)
        preview_row.addWidget(self.remove_image_button)
        preview_row.addStretch()
        outer.addLayout(preview_row)

        bar = QHBoxLayout()
        bar.setSpacing(10)

        emoji_button = QPushButton("🙂")
        emoji_button.clicked.connect(lambda: self._open_emoji_picker(emoji_button))

        attach_button = QPushButton("📎")
        attach_button.clicked.connect(self._open_attach_dialog)

        self.text_edit = PastableTextEdit()
        self.text_edit.setPlaceholderText(placeholder)
        self.text_edit.setFixedHeight(36)
        self.text_edit.setStyleSheet("""
            QTextEdit {
                background-color: transparent;
                color: white;
                border: none;
                padding: 6px 2px;
                font-size: 13px;
            }
        """)
        self.text_edit.image_pasted.connect(self._on_image_pasted)
        self.text_edit.send_requested.connect(self.send)

        self.send_button = QPushButton("➤")

        for button in (emoji_button, attach_button, self.send_button):
            button.setFixedSize(36, 36)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setStyleSheet(f"""
                QPushButton {{
                    background-color: transparent;
                    border: 1px solid {PINK};
                    border-radius: 8px;
                    color: {PINK_SOFT};
                }}
                QPushButton:hover {{ color: white; }}
                QPushButton:disabled {{ color: #666; border-color: #555; }}
            """)

        self.send_button.setStyleSheet(f"""
            QPushButton {{
                background-color: {PINK};
                border: none;
                border-radius: 8px;
                color: white;
                font-weight: bold;
            }}
            QPushButton:hover {{ background-color: {PINK_SOFT}; }}
            QPushButton:disabled {{ background-color: #555; }}
        """)
        self.send_button.clicked.connect(self.send)

        bar.addWidget(emoji_button)
        bar.addWidget(self.text_edit, stretch=1)
        bar.addWidget(attach_button)
        bar.addWidget(self.send_button)

        outer.addLayout(bar)

    def _build_full(self, placeholder):
        """Taller box with a status row — used inside TextInput.InputWindow's popup."""
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(8)

        self.text_edit = PastableTextEdit()
        self.text_edit.setPlaceholderText(placeholder)
        self.text_edit.setStyleSheet(f"""
            QTextEdit {{
                background-color: {BG_BUBBLE};
                color: white;
                border: 1px solid {PINK};
                border-radius: 8px;
                padding: 8px;
                font-size: 13px;
            }}
        """)
        self.text_edit.image_pasted.connect(self._on_image_pasted)
        self.text_edit.send_requested.connect(self.send)
        outer.addWidget(self.text_edit)

        self.preview_label = QLabel()
        self.preview_label.setVisible(False)
        self.preview_label.setMaximumHeight(80)
        outer.addWidget(self.preview_label)

        button_row = QHBoxLayout()

        self.status_label = QLabel("")
        self.status_label.setStyleSheet(f"color: {PINK_SOFT}; font-size: 11px;")
        button_row.addWidget(self.status_label)
        button_row.addStretch()

        self.remove_image_button = QPushButton("Remove image")
        self.remove_image_button.setVisible(False)
        self.remove_image_button.clicked.connect(self._remove_image)
        self.remove_image_button.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                border: 1px solid {PINK};
                border-radius: 6px;
                color: {PINK_SOFT};
                padding: 4px 10px;
            }}
            QPushButton:hover {{ color: white; }}
        """)
        button_row.addWidget(self.remove_image_button)

        self.send_button = QPushButton("Send")
        self.send_button.clicked.connect(self.send)
        self.send_button.setStyleSheet(f"""
            QPushButton {{
                background-color: {PINK};
                border: none;
                border-radius: 8px;
                color: white;
                font-weight: bold;
                padding: 6px 14px;
            }}
            QPushButton:hover {{ background-color: {PINK_SOFT}; }}
            QPushButton:disabled {{ background-color: #555; }}
        """)
        button_row.addWidget(self.send_button)

        outer.addLayout(button_row)

    # ------------------------------------------------------------------
    # Emoji picker
    # ------------------------------------------------------------------

    def _open_emoji_picker(self, anchor_button):
        picker = EmojiPicker(self)
        picker.emoji_selected.connect(self._insert_emoji)

        anchor_point = anchor_button.mapToGlobal(anchor_button.rect().bottomLeft())
        picker.move(anchor_point)
        picker.show()

    def _insert_emoji(self, emoji):
        self.text_edit.insertPlainText(emoji)
        self.text_edit.setFocus()

    # ------------------------------------------------------------------
    # Attach file
    # ------------------------------------------------------------------

    def _open_attach_dialog(self):
        pictures_dir = Path.home() / "Pictures"
        start_dir = str(pictures_dir) if pictures_dir.is_dir() else ""

        path, _ = QFileDialog.getOpenFileName(
            self, "Attach an image", start_dir, IMAGE_FILE_FILTER
        )
        if not path:
            return

        try:
            image = Image.open(path).convert("RGB")
        except Exception:
            import traceback
            traceback.print_exc()
            return

        self._set_pending_image(image)

    # ------------------------------------------------------------------
    # Image state (shared by paste and attach)
    # ------------------------------------------------------------------

    def _on_image_pasted(self, pil_image):
        self._set_pending_image(pil_image)

    def _set_pending_image(self, pil_image):
        self.pending_image = pil_image

        pixmap = pil_to_qpixmap(pil_image).scaledToHeight(
            60 if self.compact else 76, Qt.TransformationMode.SmoothTransformation
        )
        self.preview_label.setPixmap(pixmap)
        self.preview_label.setVisible(True)
        self.remove_image_button.setVisible(True)

    def _remove_image(self):
        self.pending_image = None
        self.preview_label.clear()
        self.preview_label.setVisible(False)
        self.remove_image_button.setVisible(False)

    # ------------------------------------------------------------------
    # Sending
    # ------------------------------------------------------------------

    def send(self):
        text = self.text_edit.toPlainText().strip()
        image = self.pending_image

        if not text and image is None:
            return

        # Disabled immediately — prevents a double send (double Enter,
        # double click) before the request has even fired.
        self.text_edit.setEnabled(False)
        self.send_button.setEnabled(False)

        # Lets the container react (InputWindow hides itself here;
        # PanelWindow does nothing, since it's meant to stay open).
        self.send_started.emit()

        self.text_edit.clear()
        self._remove_image()
        if self.status_label is not None:
            self.status_label.setText("")

        def _work(text=text, image=image):
            try:
                self.process_question(text, image=image)
            except Exception:
                import traceback
                traceback.print_exc()
            finally:
                self.send_finished.emit()

        threading.Thread(target=_work, daemon=True).start()

    def _on_send_finished(self):
        self.reset()

    def reset(self):
        """
        Re-enables input, clears any leftover draft, and focuses the
        field. Called both after a send completes and whenever a
        container window becomes visible again (so reopening the
        popup doesn't show a stale draft or a still-disabled field).
        """
        self.text_edit.setEnabled(True)
        self.send_button.setEnabled(True)
        self.text_edit.clear()
        self._remove_image()
        self.text_edit.setFocus()