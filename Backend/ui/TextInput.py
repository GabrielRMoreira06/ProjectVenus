"""
text_input_window.py

Floating, always-on-top input window — the direct replacement for the
old TMP_InputField in Unity. Runs on the main process (needs the Qt
mainloop), so server.py starts Flask on a separate thread and lets
QApplication.exec() own the main thread.

All paste/send/enable-disable logic now lives in MessageComposer
(compact=False here) — this file only owns the window chrome around
it: the frameless popup, the drag handle, show/hide, and the
Orchestrator pause/resume tied to that show/hide. See
MessageComposer.py for why the composer itself is shared with
PanelWindow instead of being duplicated.

Two global hotkeys are registered from here, since this is the one
place the QApplication actually lives — Ctrl+Alt+T for this input
window, Ctrl+Alt+H for PanelWindow (history/settings/preferences).
PanelWindow is constructed here (rather than having its own
QApplication) for the same reason, and is handed the SAME
process_question callback its own composer submits through.
"""

import sys

import keyboard
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QKeySequence, QShortcut
from PyQt6.QtWidgets import QApplication, QWidget, QVBoxLayout, QLabel

from ui.MessageComposer import MessageComposer
from ui.PanelWindow import PanelWindow
from ui.Theme import PINK_SOFT, BG_DARK, BG_PANEL


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

        # Orchestrator.pause/resume, injected from server.py. While
        # this window is open, Venus is presumed to be mid-conversation
        # with the user, so nothing else (monitors, system checks)
        # should jump in and interrupt. Tied to composer.send_started
        # below, same timing the old inline send() used to have.
        self.on_open = on_open or (lambda: None)
        self.on_close = on_close or (lambda: None)

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
        self.setStyleSheet(f"""
            QWidget {{ background-color: {BG_DARK}; border-radius: 10px; }}
            QLabel#dragHandle {{
                background-color: {BG_PANEL}; color: {PINK_SOFT};
                padding: 6px 10px; font-size: 12px;
                border-top-left-radius: 10px; border-top-right-radius: 10px;
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.drag_handle = DragHandle("⠿  Talk to Venus")
        layout.addWidget(self.drag_handle)

        body = QVBoxLayout()
        body.setContentsMargins(10, 10, 10, 10)
        layout.addLayout(body)

        self.composer = MessageComposer(
            process_question,
            compact=False,
            placeholder="Say something to Venus... (Ctrl+V pastes text or an image, Enter sends)",
        )
        # Fires the instant send() commits, before process_question is
        # even called — the window disappears immediately rather than
        # waiting on Gemini, since the actual reply shows up via
        # Unity's speech bubble/audio, not this window.
        self.composer.send_started.connect(self.hide_window)
        body.addWidget(self.composer)

        # Escape hides the window without sending.
        QShortcut(QKeySequence(Qt.Key.Key_Escape), self, activated=self.hide_window)

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
        QTimer.singleShot(0, self.composer.reset)  # clears any stale draft, focuses the field

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
    duplicating anything. PanelWindow (below) is handed this same
    callback, so its own composer submits through the identical path.

    `on_open`/`on_close`: typically orchestrator.pause/orchestrator.resume
    — pauses dispatch while THIS window is visible, so nothing interrupts
    the user mid-message (this is also what covers the first-boot name
    question, since that window opens the same way). PanelWindow does
    NOT get this treatment — see PanelWindow.py's docstring for why.

    `open_automatically`: used on first boot, when Venus is waiting for
    the user to type her a name — without this, the user wouldn't know
    they need to press the hotkey to answer.

    This is also where PanelWindow (history/settings/preferences) is
    constructed and hooked to its own hotkey. It has to happen here,
    not in a separate start_panel_window() call — only one
    QApplication can exist per process, and this one already owns the
    event loop (sys.exit(app.exec()) below blocks until the app quits).
    """
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