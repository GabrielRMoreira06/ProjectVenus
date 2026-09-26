"""
AppBootstrap.py

Owns the single QApplication for the whole app, every top-level PyQt6
window (InputWindow, PanelWindow, NotepadWindow), and their global
hotkeys. This has to live in one place: only one QApplication can
exist per process, and app.exec() has to be the last call on the main
thread — so whatever creates the QApplication ends up owning every
window that shares it. Previously this logic was bolted onto
TextInput.py's start_input_window(), which grew a window's worth of
unrelated setup every time a new floating window was added.

Server.py calls run() as the last thing on the main thread.
"""

import sys

import keyboard
from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication

from ui.TextInput import InputWindow
from ui.PanelWindow import PanelWindow
from ui.Notepad import NotepadWindow


def run(process_question, open_automatically=False):
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    input_window = InputWindow(process_question)
    keyboard.add_hotkey("ctrl+alt+t", input_window.toggle_requested.emit)
    print("[AppBootstrap] Hotkey 'ctrl+alt+t' registered globally (InputWindow).")

    panel_window = PanelWindow(process_question)
    keyboard.add_hotkey("ctrl+alt+h", panel_window.toggle_requested.emit)
    print("[AppBootstrap] Hotkey 'ctrl+alt+h' registered globally (PanelWindow).")

    notepad_window = NotepadWindow()
    keyboard.add_hotkey("ctrl+alt+n", notepad_window.toggle_requested.emit)
    print("[AppBootstrap] Hotkey 'ctrl+alt+n' registered globally (Notepad).")

    if open_automatically:
        QTimer.singleShot(500, input_window.show_window)

    sys.exit(app.exec())