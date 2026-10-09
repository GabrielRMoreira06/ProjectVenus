"""
WallpaperManager.py

Plays a video from the persistent WallpaperStore behind the desktop
icons, one mpv window per monitor, using Venus's existing
QApplication. start() picks a random one; play() switches to a
specific one at runtime. Pauses per monitor while a maximized/
fullscreen window covers it.

Needs libmpv-2.dll (or mpv-2.dll) in Backend/ — pip install python-mpv pywin32
"""

import ctypes
import locale
import os
import random
from ctypes import wintypes

from config import DATA_DIR
from ai.WallpaperStore import wallpaper_store

os.environ["PATH"] = str(DATA_DIR) + os.pathsep + os.environ["PATH"]

import mpv
import win32api
import win32con
import win32gui
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QColor, QPalette
from PyQt6.QtWidgets import QWidget

CHECK_INTERVAL_MS = 1000
DEBUG = False

IGNORE_CLASSES = {"Progman", "WorkerW", "Shell_TrayWnd", "Shell_SecondaryTrayWnd"}

dwmapi = ctypes.windll.dwmapi
DWMWA_CLOAKED = 14


def _find_workerw():
    progman = win32gui.FindWindow("Progman", None)
    win32gui.SendMessageTimeout(progman, 0x052C, 0, 0, win32con.SMTO_NORMAL, 1000)

    found = []

    def callback(hwnd, _):
        if win32gui.FindWindowEx(hwnd, 0, "SHELLDLL_DefView", None):
            worker = win32gui.FindWindowEx(0, hwnd, "WorkerW", None)
            if worker:
                found.append(worker)

    win32gui.EnumWindows(callback, None)

    if found:
        return found[0]
    return win32gui.FindWindowEx(progman, 0, "WorkerW", None) or progman


def _list_monitors():
    return [(int(m), rect) for m, _, rect in win32api.EnumDisplayMonitors()]


def _is_cloaked(hwnd):
    cloaked = wintypes.DWORD(0)
    try:
        dwmapi.DwmGetWindowAttribute(
            wintypes.HWND(hwnd), DWMWA_CLOAKED,
            ctypes.byref(cloaked), ctypes.sizeof(cloaked),
        )
    except OSError:
        return False
    return cloaked.value != 0


def _get_covered_monitors(ignore_hwnds):
    covered = set()

    def callback(hwnd, _):
        try:
            if hwnd in ignore_hwnds:
                return
            if not win32gui.IsWindowVisible(hwnd) or win32gui.IsIconic(hwnd):
                return
            if win32gui.GetClassName(hwnd) in IGNORE_CLASSES:
                return
            if _is_cloaked(hwnd):
                return

            ex_style = win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)
            if ex_style & win32con.WS_EX_TOOLWINDOW:
                return

            is_maximized = win32gui.GetWindowPlacement(hwnd)[1] == win32con.SW_SHOWMAXIMIZED

            monitor = win32api.MonitorFromWindow(hwnd, win32con.MONITOR_DEFAULTTONEAREST)
            left, top, right, bottom = win32api.GetMonitorInfo(monitor)["Monitor"]
            x1, y1, x2, y2 = win32gui.GetWindowRect(hwnd)
            is_fullscreen = x1 <= left and y1 <= top and x2 >= right and y2 >= bottom

            if is_maximized or is_fullscreen:
                covered.add(int(monitor))
                if DEBUG:
                    print(f"[WallpaperManager] pause: {win32gui.GetClassName(hwnd)!r} "
                          f"- {win32gui.GetWindowText(hwnd)!r}")
        except Exception:
            pass

    win32gui.EnumWindows(callback, None)
    return covered


class _MonitorWallpaper:

    def __init__(self, hmonitor, rect, workerw, video_path):
        self.hmonitor = hmonitor
        self.rect = rect
        self.workerw = workerw

        self.container = QWidget()
        self.container.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        self.container.setAttribute(Qt.WidgetAttribute.WA_NativeWindow, True)
        palette = self.container.palette()
        palette.setColor(QPalette.ColorRole.Window, QColor("black"))
        self.container.setPalette(palette)
        self.container.setAutoFillBackground(True)

        self.container.show()
        self.hwnd = int(self.container.winId())
        self._embed_into_desktop()

        self.player = mpv.MPV(
            wid=str(self.hwnd),
            loop_file="inf",
            mute="yes",
            hwdec="auto-safe",
            vo="gpu",
            panscan=1.0,
            keepaspect="yes",
            osc="no",
            input_default_bindings="no",
            input_vo_keyboard="no",
            cursor_autohide="no",
            log_handler=print if DEBUG else None,
        )
        self.set_video(video_path)

    def _embed_into_desktop(self):
        win32gui.SetParent(self.hwnd, self.workerw)

        style = win32gui.GetWindowLong(self.hwnd, win32con.GWL_STYLE)
        style = (style & ~win32con.WS_POPUP) | win32con.WS_CHILD
        win32gui.SetWindowLong(self.hwnd, win32con.GWL_STYLE, style)

        left, top, right, bottom = self.rect
        x, y = win32gui.ScreenToClient(self.workerw, (left, top))
        win32gui.SetWindowPos(
            self.hwnd, 0, x, y, right - left, bottom - top,
            win32con.SWP_NOZORDER | win32con.SWP_NOACTIVATE
            | win32con.SWP_FRAMECHANGED | win32con.SWP_SHOWWINDOW,
        )

    def set_video(self, video_path):
        self.player.pause = False
        self.player.play(video_path)

    def set_pause(self, should_pause):
        if bool(self.player.pause) != should_pause:
            self.player.pause = should_pause

    def close(self):
        try:
            self.player.terminate()
        except Exception:
            pass
        self.container.close()


class WallpaperManager:

    def __init__(self, store=wallpaper_store):
        self.store = store
        self.wallpapers = []
        self.own_hwnds = set()
        self._timer = None

    def start(self):
        candidates = [v for v in self.store.get_all() if os.path.isfile(v)]

        if not candidates:
            print("[WallpaperManager] No valid videos in the wallpaper list — skipping.")
            return

        self._launch(random.choice(candidates))

    def play(self, video_path):
        if not os.path.isfile(video_path):
            print(f"[WallpaperManager] File not found: '{video_path}'.")
            return

        if not self.wallpapers:
            self._launch(video_path)
            return

        print(f"[WallpaperManager] Switching to '{video_path}'.")

        for wallpaper in self.wallpapers:
            wallpaper.set_video(video_path)

    def _launch(self, video_path):
        print(f"[WallpaperManager] Playing '{video_path}'.")

        # python-mpv requires LC_NUMERIC "C", and Qt can override it.
        locale.setlocale(locale.LC_NUMERIC, "C")

        workerw = _find_workerw()
        self.wallpapers = [
            _MonitorWallpaper(hmon, rect, workerw, video_path)
            for hmon, rect in _list_monitors()
        ]
        self.own_hwnds = {w.hwnd for w in self.wallpapers}

        if self._timer is None:
            self._timer = QTimer()
            self._timer.timeout.connect(self._check_monitors)
        self._timer.start(CHECK_INTERVAL_MS)

    def stop(self):
        if self._timer is not None:
            self._timer.stop()

        for wallpaper in self.wallpapers:
            wallpaper.close()

        self.wallpapers = []

    def _check_monitors(self):
        covered = _get_covered_monitors(self.own_hwnds)

        for wallpaper in self.wallpapers:
            wallpaper.set_pause(wallpaper.hmonitor in covered)


# Shared instance, same pattern as `preferences`/`mood` elsewhere —
# AppBootstrap starts it, WallpaperPage tells it what to play.
wallpaper_manager = WallpaperManager()