"""
AppBootstrap.py

Owns the single QApplication for the whole app, the PanelWindow and
its global hotkey, the video WallpaperManager, and the DeadLineManager.
This has to live in one place: only one QApplication can exist per
process, and app.exec() has to be the last call on the main thread —
so whatever creates the QApplication ends up owning every window that
shares it.

Server.py calls run() as the last thing on the main thread.
"""

import sys

import keyboard
from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication

from ui.PanelWindow import PanelWindow
from ui.componenets.DeadLine import DeadLineManager
from ai.wallpaper.WallpaperManager import wallpaper_manager


def run(process_question, open_automatically=False):
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    try:
        wallpaper_manager.start()
    except Exception:
        import traceback
        traceback.print_exc()
    app.aboutToQuit.connect(wallpaper_manager.stop)

    dead_line_manager = DeadLineManager()

    panel_window = PanelWindow(process_question)
    keyboard.add_hotkey("ctrl+alt+h", panel_window.toggle_requested.emit)
    print("[AppBootstrap] Hotkey 'ctrl+alt+h' registered globally (PanelWindow).")

    if open_automatically:
        QTimer.singleShot(500, panel_window.toggle_requested.emit)

    sys.exit(app.exec())