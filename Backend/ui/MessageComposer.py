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

Attach dialog accepts images AND PDFs, but they take different paths:
an image is opened as a PIL.Image and sent straight through to
process_question(image=...), same as a pasted image — it ends up as
multimodal content in worker.chat. A PDF is NOT sent that way: it's
resolved to a short text summary (via ai/PdfSummarizer.py, its own
one-off Gemini call, outside worker.chat) right here in send(), and
only that summary — folded into the plain text as a
"[SYSTEM MESSAGE: ...]" block — reaches process_question. Server.py
and GeminiWorker never see the PDF itself.
"""

import threading
from pathlib import Path

from PIL import Image
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QImage
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QTextEdit, QPushButton, QLabel, QFileDialog,
)
import qtawesome as qta
from PyQt6.QtCore import Qt, QSize, pyqtSignal
from ui.ImageUtils import qimage_to_pil, pil_to_qpixmap
import ui.Theme as Theme
from ai.PdfSummarizer import pdf_summarizer

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

ATTACH_FILE_FILTER = "Images and PDFs (*.png *.jpg *.jpeg *.webp *.bmp *.gif *.pdf)"


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
    - The widget grows in height as text wraps onto more lines (up to
      max_lines), instead of staying a fixed height with an internal
      scrollbar from the first character.
    """

    image_pasted = pyqtSignal(object)  # emits a PIL.Image
    send_requested = pyqtSignal()

    def __init__(self, min_lines=1, max_lines=5, parent=None):
        """
        min_lines/max_lines bound the auto-grow range: the box starts
        at min_lines tall and expands as the user types, up to
        max_lines, at which point a scrollbar takes over instead of
        the widget growing further.
        """
        super().__init__(parent)
        self._min_lines = min_lines
        self._max_lines = max_lines

        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)

        # documentSizeChanged fires on every content change (typing,
        # pasting, programmatic clear()) - textChanged would also work
        # but fires before layout has settled on the wrapped line
        # count, which would make the height lag one keystroke behind.
        #
        # We don't resize synchronously from inside this signal: Qt
        # can emit it mid-layout/mid-stylesheet-polish, and calling
        # setFixedHeight() right then re-enters that same layout pass.
        # That reentrancy is what was causing the stylesheet (icons,
        # borders) to intermittently fall back to native/unstyled
        # rendering - not a crash, just a corrupted paint. Deferring
        # the actual resize to the next event-loop turn via
        # QTimer.singleShot(0, ...) lets the current layout/style pass
        # finish first, so it doesn't fight itself.
        self.document().documentLayout().documentSizeChanged.connect(self._schedule_adjust_height)
        self._adjust_height()

    def _line_height(self):
        return self.fontMetrics().lineSpacing()

    def _schedule_adjust_height(self, *_args):
        QTimer.singleShot(0, self._adjust_height)

    def _adjust_height(self, *_args):
        # document().size().height() already bakes in documentMargin()
        # on both top and bottom - it is NOT extra padding on top of
        # that, so it must only be added once here (for min/max_height,
        # which are derived from line count rather than from the
        # document itself) and never added again on top of
        # content_height, or every size ends up ~2*doc_margin too
        # tall (visually: the box looks like it starts a whole line
        # taller than it should).
        margins = self.contentsMargins()
        doc_margin = self.document().documentMargin()
        frame = self.frameWidth()
        chrome = margins.top() + margins.bottom() + 2 * frame

        min_height = self._line_height() * self._min_lines + 2 * doc_margin + chrome
        max_height = self._line_height() * self._max_lines + 2 * doc_margin + chrome
        content_height = self.document().size().height() + chrome

        target_height = max(min_height, min(content_height, max_height))
        self.setFixedHeight(int(round(target_height)))

        self.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
            if content_height > max_height
            else Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )

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

    Short-lived by nature (opens, picks/dismisses, closes), so it just
    reads Theme.* once at build time rather than subscribing to
    theme_signals — nothing to keep in sync for a widget that won't
    outlive a single click.
    """

    emoji_selected = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent, Qt.WindowType.Popup)

        self.setStyleSheet(f"""
            QWidget {{
                background-color: {Theme.BG_PANEL};
                border: 1px solid {Theme.PINK};
                border-radius: 8px;
            }}
            QPushButton {{
                background: transparent;
                border: none;
                font-size: 18px;
            }}
            QPushButton:hover {{
                background-color: {Theme.BG_BUBBLE};
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
        self.pending_pdf_path = None
        self.status_label = None  # only exists in full mode — see _build_full

        self.send_finished.connect(self._on_send_finished)

        if compact:
            self._build_compact(placeholder)
        else:
            self._build_full(placeholder)

        Theme.theme_signals.changed.connect(self._apply_style)
        self._apply_style()  # apply immediately too - don't rely solely on the theme signal firing

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

        preview_row.addWidget(self.preview_label)
        preview_row.addWidget(self.remove_image_button)
        preview_row.addStretch()
        outer.addLayout(preview_row)

        bar = QHBoxLayout()
        bar.setSpacing(10)

        self.emoji_button = QPushButton()
        self.emoji_button.clicked.connect(lambda: self._open_emoji_picker(self.emoji_button))

        self.attach_button = QPushButton()
        self.attach_button.clicked.connect(self._open_attach_dialog)
        self.attach_button.clicked.connect(self._open_attach_dialog)

        # min_lines=1/max_lines=5: starts as a single-line bar and
        # grows upward as the user types multi-line messages, instead
        # of staying pinned at a fixed height with a scrollbar from
        # line two.
        self.text_edit = PastableTextEdit(min_lines=1, max_lines=5)
        self.text_edit.setPlaceholderText(placeholder)
        self.text_edit.image_pasted.connect(self._on_image_pasted)
        self.text_edit.send_requested.connect(self.send)

        self.send_button = QPushButton()

        # Smaller than before (was 36) so the whole bar sits closer to
        # the height of one line of text instead of towering over it.
        for button in (self.emoji_button, self.attach_button, self.send_button):
            button.setFixedSize(28, 28)
            button.setCursor(Qt.CursorShape.PointingHandCursor)

        self.send_button.clicked.connect(self.send)

        # Vertically centered rather than bottom-aligned: with the
        # icons now shorter than a single line of text, bottom-aligning
        # them left visible daylight above each icon. Centering keeps
        # everything sitting on the same visual midline while the text
        # field is at its 1-line resting height, and still looks fine
        # once it grows.
        bar.addWidget(self.emoji_button, alignment=Qt.AlignmentFlag.AlignVCenter)
        bar.addWidget(self.text_edit, stretch=1, alignment=Qt.AlignmentFlag.AlignVCenter)
        bar.addWidget(self.attach_button, alignment=Qt.AlignmentFlag.AlignVCenter)
        bar.addWidget(self.send_button, alignment=Qt.AlignmentFlag.AlignVCenter)

        outer.addLayout(bar)

    def _build_full(self, placeholder):
        """Taller box with a status row — used inside TextInput.InputWindow's popup."""
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(8)

        # min_lines=3/max_lines=10: this popup already started taller
        # than the compact bar, so it gets a taller auto-grow range
        # before it starts scrolling internally.
        self.text_edit = PastableTextEdit(min_lines=3, max_lines=10)
        self.text_edit.setPlaceholderText(placeholder)
        self.text_edit.image_pasted.connect(self._on_image_pasted)
        self.text_edit.send_requested.connect(self.send)
        outer.addWidget(self.text_edit)

        self.preview_label = QLabel()
        self.preview_label.setVisible(False)
        self.preview_label.setMaximumHeight(80)
        outer.addWidget(self.preview_label)

        button_row = QHBoxLayout()

        self.status_label = QLabel("")
        button_row.addWidget(self.status_label)
        button_row.addStretch()

        self.remove_image_button = QPushButton("Remove image")
        self.remove_image_button.setVisible(False)
        self.remove_image_button.clicked.connect(self._remove_image)
        button_row.addWidget(self.remove_image_button)

        self.send_button = QPushButton("Send")
        self.send_button.clicked.connect(self.send)
        button_row.addWidget(self.send_button)

        outer.addLayout(button_row)

    # ------------------------------------------------------------------
    # Theming
    # ------------------------------------------------------------------

    def _apply_style(self):
        if self.compact:
            self._apply_compact_style()
        else:
            self._apply_full_style()

    def _apply_compact_style(self):
        self.remove_image_button.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                border: 1px solid {Theme.PINK};
                border-radius: 11px;
                color: {Theme.PINK_SOFT};
            }}
            QPushButton:hover {{ color: white; }}
        """)

        self.emoji_button.setIcon(qta.icon("fa5s.smile", color=Theme.PINK_SOFT, color_active="white"))
        self.emoji_button.setIconSize(QSize(14, 14))

        self.attach_button.setIcon(qta.icon("fa5s.paperclip", color=Theme.PINK_SOFT, color_active="white"))
        self.attach_button.setIconSize(QSize(14, 14))

        self.text_edit.setStyleSheet("""
            QTextEdit {
                background-color: transparent;
                color: white;
                border: none;
                padding: 2px 2px;
                font-size: 13px;
            }
        """)

        self.send_button.setIcon(qta.icon("fa5s.paper-plane", color="white", color_disabled="#888888"))
        self.send_button.setIconSize(QSize(13, 13))

        for button in (self.emoji_button, self.attach_button):
            button.setStyleSheet(f"""
                QPushButton {{
                    background-color: transparent;
                    border: 1px solid {Theme.PINK};
                    border-radius: 14px;
                    color: {Theme.PINK_SOFT};
                }}
                QPushButton:hover {{ color: white; }}
                QPushButton:disabled {{ color: #666; border-color: #555; }}
            """)

        self.send_button.setStyleSheet(f"""
            QPushButton {{
                background-color: {Theme.PINK};
                border: none;
                border-radius: 14px;
                color: white;
                font-weight: bold;
            }}
            QPushButton:hover {{ background-color: {Theme.PINK_SOFT}; }}
            QPushButton:disabled {{ background-color: #555; }}
        """)

    def _apply_full_style(self):
        self.text_edit.setStyleSheet(f"""
            QTextEdit {{
                background-color: {Theme.BG_BUBBLE};
                color: white;
                border: 1px solid {Theme.PINK};
                border-radius: 8px;
                padding: 8px;
                font-size: 13px;
            }}
        """)

        if self.status_label is not None:
            self.status_label.setStyleSheet(f"color: {Theme.PINK_SOFT}; font-size: 11px;")

        self.remove_image_button.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                border: 1px solid {Theme.PINK};
                border-radius: 6px;
                color: {Theme.PINK_SOFT};
                padding: 4px 10px;
            }}
            QPushButton:hover {{ color: white; }}
        """)

        self.send_button.setStyleSheet(f"""
            QPushButton {{
                background-color: {Theme.PINK};
                border: none;
                border-radius: 8px;
                color: white;
                font-weight: bold;
                padding: 6px 14px;
            }}
            QPushButton:hover {{ background-color: {Theme.PINK_SOFT}; }}
            QPushButton:disabled {{ background-color: #555; }}
        """)

    # ------------------------------------------------------------------
    # Emoji picker
    # ------------------------------------------------------------------

    def _open_emoji_picker(self, anchor_button):
        picker = EmojiPicker(self)
        picker.emoji_selected.connect(self._insert_emoji)
        picker.adjustSize()

        # Map the top-left corner of the button to global screen coordinates
        button_top_left = anchor_button.mapToGlobal(anchor_button.rect().topLeft())

        # Place the bottom of the picker above the top of the button (with a 6px margin)
        x = button_top_left.x()
        y = button_top_left.y() - picker.height() - 6

        picker.move(x, y)
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
            self, "Attach a file", start_dir, ATTACH_FILE_FILTER
        )
        if not path:
            return

        if path.lower().endswith(".pdf"):
            self._set_pending_pdf(path)
            return

        try:
            image = Image.open(path).convert("RGB")
        except Exception:
            import traceback
            traceback.print_exc()
            return

        self._set_pending_image(image)

    # ------------------------------------------------------------------
    # Attachment state (image XOR pdf — only one pending at a time)
    # ------------------------------------------------------------------

    def _on_image_pasted(self, pil_image):
        self._set_pending_image(pil_image)

    def _set_pending_image(self, pil_image):
        self.pending_pdf_path = None
        self.pending_image = pil_image

        pixmap = pil_to_qpixmap(pil_image).scaledToHeight(
            60 if self.compact else 76, Qt.TransformationMode.SmoothTransformation
        )
        self.preview_label.setPixmap(pixmap)
        self.preview_label.setVisible(True)
        self.remove_image_button.setVisible(True)

    def _set_pending_pdf(self, path):
        """
        Just remembers the path for send() to resolve later — no
        summarization happens here. The preview only shows the
        filename; there's nothing to thumbnail.
        """
        self.pending_image = None
        self.pending_pdf_path = path

        self.preview_label.setText(f"📄 {Path(path).name}")
        self.preview_label.setVisible(True)
        self.remove_image_button.setVisible(True)

    def _remove_image(self):
        self.pending_image = None
        self.pending_pdf_path = None
        self.preview_label.clear()
        self.preview_label.setVisible(False)
        self.remove_image_button.setVisible(False)

    # ------------------------------------------------------------------
    # Sending
    # ------------------------------------------------------------------

    def send(self):
        text = self.text_edit.toPlainText().strip()
        image = self.pending_image
        pdf_path = self.pending_pdf_path

        if not text and image is None and pdf_path is None:
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

        def _work(text=text, image=image, pdf_path=pdf_path):
            try:
                if pdf_path is not None:
                    # Resolved here, on this background thread, NOT
                    # inside process_question/worker.run — the PDF
                    # itself never reaches worker.chat, only whatever
                    # short summary comes back.
                    summary = pdf_summarizer.summarize(pdf_path)
                    filename = Path(pdf_path).name

                    note = (
                        f"[SYSTEM MESSAGE: user attached the PDF '{filename}'. Summary: {summary}]"
                        if summary else
                        f"[SYSTEM MESSAGE: user attached the PDF '{filename}', but no text could be extracted from it.]"
                    )

                    text = f"{text}\n\n{note}" if text else note
                    image = None

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