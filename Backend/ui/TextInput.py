"""
text_input_window.py

Floating, always-on-top input window — the direct replacement for the
old TMP_InputField in Unity. Runs on the main process (needs the Qt
mainloop), so server.py starts Flask on a separate thread and lets
QApplication.exec() own the main thread.

Supports pasting TEXT and an IMAGE (Ctrl+V): a pasted image
(screenshot, image copied from a browser, ...) is sent alongside the
text through the SAME pipeline any other user question uses — this
window doesn't know about Orchestrator or Category at all, it just
calls whatever `process_question(text, image=None)` callback it was
given. That callback is server.py's job to wire up (eventually to
`orchestrator.add(Category.USER, ..., sync=True)`).

A global hotkey (Ctrl+Alt+T by default) shows/hides the window — lives
entirely here, no dependency on Unity for it.
"""

import sys
from io import BytesIO

import keyboard
from PIL import Image
from PyQt6.QtCore import Qt, QByteArray, QBuffer, QTimer, pyqtSignal
from PyQt6.QtGui import QPixmap, QImage, QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QTextEdit, QPushButton, QLabel,
)


def qimage_to_pil(qimage: QImage) -> Image.Image:
    """
    Converts a QImage from the clipboard into a PIL.Image — the same
    type screen_capture.capture_screen() already returns, and that
    GeminiWorker.run() already accepts as `image=`.
    """
    buffer = QByteArray()
    qbuffer = QBuffer(buffer)
    qbuffer.open(QBuffer.OpenModeFlag.WriteOnly)
    qimage.save(qbuffer, "PNG")
    qbuffer.close()

    return Image.open(BytesIO(bytes(buffer))).convert("RGB")


class PastableTextEdit(QTextEdit):
    """
    A normal QTextEdit, except:
    - Ctrl+V first checks whether the clipboard holds an IMAGE — if it
      does, it's emitted via a signal instead of being pasted as text
      (which would otherwise produce garbage or nothing at all).
    - Enter sends (emits send_requested) instead of inserting a
      newline; Shift+Enter still inserts one normally. This is handled
      here, in keyPressEvent, rather than via QShortcut: QTextEdit
      consumes Key_Return itself in its own keyPressEvent, so a
      WidgetShortcut on Key_Return never reliably wins against it.
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


class DragHandle(QLabel):
    """
    A frameless window has no native titlebar to drag — this thin bar
    at the top does that job: clicking and dragging here moves the
    whole window. Uses `self.window()` (not `self.parent()`) since
    that's the real top-level widget that needs to move.
    """

    def __init__(self, text):
        super().__init__(text)
        self.setObjectName("dragHandle")
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self._click_offset = None

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._click_offset = event.globalPosition().toPoint() - self.window().pos()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)

    def mouseMoveEvent(self, event):
        if self._click_offset is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.window().move(event.globalPosition().toPoint() - self._click_offset)

    def mouseReleaseEvent(self, event):
        self._click_offset = None
        self.setCursor(Qt.CursorShape.OpenHandCursor)


class InputWindow(QWidget):

    # Emitted from the 'keyboard' library's thread (a native OS hook,
    # NOT a QThread). Calling widget methods directly from another
    # thread is unsafe and will glitch/break window painting — so the
    # hotkey never calls self.toggle() directly, only .emit() here. Qt
    # automatically queues the real call to toggle() onto the main
    # thread, since the signal is emitted from a thread other than the
    # one that owns this object (Auto Connection becomes Queued
    # Connection in that case).
    toggle_requested = pyqtSignal()

    def __init__(self, process_question, on_open=None, on_close=None):
        super().__init__()

        # Callback provided by server.py — receives (text, image=None)
        # and handles everything (submitting to Orchestrator, delivering
        # the result to Unity). This window doesn't need to know how the
        # response actually reaches Unity.
        self.process_question = process_question

        # Orchestrator.pause/resume, injected the same way — this
        # window doesn't import Orchestrator either. While the window
        # is open, Venus is presumed to be mid-conversation with the
        # user, so nothing else (monitors, system checks) should jump
        # in and interrupt. on_close always fires before send() spawns
        # the background thread that actually submits the question, so
        # the queue is already unpaused by the time anything needs it.
        self.on_open = on_open or (lambda: None)
        self.on_close = on_close or (lambda: None)

        self.pending_image = None
        self._positioned = False  # only auto-center the first time

        self.setWindowTitle("Talk to Venus")
        self.setWindowFlags(
            Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
        )
        # Without this, a top-level, frameless QWidget often ignores the
        # background/border-radius from the stylesheet and paints as a
        # solid black rectangle (the "raw" window background, never
        # replaced by the QSS) — the children exist, they just don't
        # show up on top of it.
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setFixedSize(420, 246)

        self.toggle_requested.connect(self.toggle)
        self.setStyleSheet("""
            QWidget { background-color: #1e1e24; border-radius: 10px; }
            QLabel#dragHandle { background-color: #16161c; color: #ccc;
                                 padding: 6px 10px; font-size: 12px;
                                 border-top-left-radius: 10px; border-top-right-radius: 10px; }
            QTextEdit { background-color: #2a2a32; color: #f2f2f2;
                        border-radius: 8px; padding: 8px; font-size: 13px; }
            QPushButton { background-color: #ff6fa5; color: white;
                          border-radius: 8px; padding: 6px 14px; font-weight: bold; }
            QPushButton:hover { background-color: #ff85b3; }
            QPushButton:disabled { background-color: #555; }
            QLabel#status { color: #999; font-size: 11px; }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.drag_handle = DragHandle("⠿  Talk to Venus")
        layout.addWidget(self.drag_handle)

        body = QVBoxLayout()
        body.setContentsMargins(10, 10, 10, 10)
        layout.addLayout(body)

        self.text_edit = PastableTextEdit()
        self.text_edit.setPlaceholderText(
            "Say something to Venus... (Ctrl+V pastes text or an image, Enter sends)"
        )
        self.text_edit.image_pasted.connect(self._on_image_pasted)
        self.text_edit.send_requested.connect(self.send)
        body.addWidget(self.text_edit)

        self.preview_label = QLabel()
        self.preview_label.setVisible(False)
        self.preview_label.setMaximumHeight(80)
        body.addWidget(self.preview_label)

        button_row = QHBoxLayout()

        self.status_label = QLabel("")
        self.status_label.setObjectName("status")
        button_row.addWidget(self.status_label)
        button_row.addStretch()

        self.remove_image_button = QPushButton("Remove image")
        self.remove_image_button.setVisible(False)
        self.remove_image_button.clicked.connect(self._remove_image)
        button_row.addWidget(self.remove_image_button)

        self.send_button = QPushButton("Send")
        self.send_button.clicked.connect(self.send)
        button_row.addWidget(self.send_button)

        body.addLayout(button_row)

        # Enter sends (see PastableTextEdit.keyPressEvent); Escape hides
        # the window without sending.
        QShortcut(QKeySequence(Qt.Key.Key_Escape), self, activated=self.hide_window)

    # ------------------------------------------------------------------
    # Image pasting
    # ------------------------------------------------------------------

    def _on_image_pasted(self, pil_image: Image.Image):
        self.pending_image = pil_image

        qimage = QImage(
            pil_image.tobytes("raw", "RGB"),
            pil_image.width, pil_image.height,
            pil_image.width * 3,
            QImage.Format.Format_RGB888,
        ).copy()  # copy() to detach from the python buffer, which may be GC'd

        pixmap = QPixmap.fromImage(qimage).scaledToHeight(
            76, Qt.TransformationMode.SmoothTransformation
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

        # Disables input RIGHT AWAY, before any network call — prevents
        # a double send (double Enter, double click) while the request
        # hasn't even been fired yet.
        self.text_edit.setEnabled(False)
        self.send_button.setEnabled(False)

        # Disappears IMMEDIATELY, without waiting for Gemini's response
        # — what actually shows the response is Unity's speech
        # bubble/audio (via /response), not this window. Waiting here
        # would just leave the window hanging on screen for 1-3s for
        # nothing.
        self.hide_window()
        self.text_edit.clear()
        self._remove_image()
        self.status_label.setText("")

        # `process_question` may block for a couple of seconds (it's a
        # synchronous, blocking call into the orchestrator) — runs on a
        # separate thread so it doesn't freeze the Qt UI, even with the
        # window already hidden.
        def _work(text=text, image=image):
            try:
                self.process_question(text, image=image)
            except Exception:
                import traceback
                traceback.print_exc()

        import threading
        threading.Thread(target=_work, daemon=True).start()

    # ------------------------------------------------------------------
    # Show/hide
    # ------------------------------------------------------------------

    def show_window(self):
        self.text_edit.setEnabled(True)
        self.send_button.setEnabled(True)

        if not self._positioned:
            screen = QApplication.primaryScreen().availableGeometry()
            self.move(screen.center().x() - self.width() // 2, screen.height() - self.height() - 60)
            self._positioned = True

        self.show()
        self.raise_()
        self.activateWindow()
        QTimer.singleShot(0, lambda: (self.text_edit.clear(), self.text_edit.setFocus()))

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
    """
    Entry point called by server.py. RUNS ON THE MAIN THREAD —
    QApplication.exec() blocks until the app closes, so Flask needs to
    already be running on a separate thread before this is called.

    `process_question`: same logic used by the /perguntar route,
    injected from outside — guarantees the window goes through the
    EXACT same path (including any first-boot flow), without
    duplicating anything.

    `on_open`/`on_close`: typically orchestrator.pause/orchestrator.resume
    — pauses dispatch while the window is visible, so nothing interrupts
    the user mid-message (this is also what covers the first-boot name
    question, since that window opens the same way).

    `open_automatically`: used on first boot, when Venus is waiting for
    the user to type her a name — without this, the user wouldn't know
    they need to press the hotkey to answer.
    """
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    window = InputWindow(process_question, on_open=on_open, on_close=on_close)

    keyboard.add_hotkey(hotkey, window.toggle_requested.emit)
    print(f"[text_input_window] Hotkey '{hotkey}' registered globally.")

    if open_automatically:
        QTimer.singleShot(500, window.show_window)

    sys.exit(app.exec())