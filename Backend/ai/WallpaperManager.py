"""
Video Wallpaper for Windows using mpv (smoother loop than QMediaPlayer)

- Plays a video on repeat behind the desktop icons
- One window per monitor
- Automatically pauses (per monitor) when a window is maximized
  or in full-screen covering that monitor
- System tray icon: pause/resume, auto-pause, change video, exit

Requirements:
    pip install PyQt6 pywin32 python-mpv
    + libmpv: download "libmpv-2.dll" (or "mpv-2.dll") and place it in the same folder
      as this script (or in a folder included in PATH).
      Builds: https://sourceforge.net/projects/mpv-player-windows/files/libmpv/

Usage:
    python video_wallpaper_mpv.py "C:\\videos\\background.mp4"
"""

import ctypes
import json
import locale
import os
import sys
from ctypes import wintypes

# Allow Python to locate the mpv DLL in the script's directory
os.environ["PATH"] = os.path.dirname(os.path.abspath(__file__)) + os.pathsep + os.environ["PATH"]

import mpv  # noqa: E402
import win32api  # noqa: E402
import win32con  # noqa: E402
import win32gui  # noqa: E402
from PyQt6.QtCore import QTimer  # noqa: E402
from PyQt6.QtGui import QAction, QColor, QPalette  # noqa: E402
from PyQt6.QtWidgets import (  # noqa: E402
    QApplication,
    QFileDialog,
    QMenu,
    QStyle,
    QSystemTrayIcon,
    QWidget,
)
from PyQt6.QtCore import Qt  # noqa: E402

# ----------------------------------------------------------------------------
# Settings
# ----------------------------------------------------------------------------
CHECK_INTERVAL_MS = 1000
DEBUG = False  # True: prints which window is triggering the pause

CONFIG_PATH = os.path.join(os.environ.get("APPDATA", "."), "video_wallpaper.json")

IGNORE_CLASSES = {
    "Progman",
    "WorkerW",
    "Shell_TrayWnd",
    "Shell_SecondaryTrayWnd",
}

dwmapi = ctypes.windll.dwmapi
DWMWA_CLOAKED = 14


# ----------------------------------------------------------------------------
# Config
# ----------------------------------------------------------------------------
def load_video_path():
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f).get("video")
    except (OSError, ValueError):
        return None


def save_video_path(path):
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump({"video": path}, f)
    except OSError:
        pass


# ----------------------------------------------------------------------------
# Windows Helpers
# ----------------------------------------------------------------------------
def find_workerw():
    progman = win32gui.FindWindow("Progman", None)
    win32gui.SendMessageTimeout(progman, 0x052C, 0, 0, win32con.SMTO_NORMAL, 1000)

    found_windows = []

    def enum_callback(hwnd, _):
        if win32gui.FindWindowEx(hwnd, 0, "SHELLDLL_DefView", None):
            worker_window = win32gui.FindWindowEx(0, hwnd, "WorkerW", None)
            if worker_window:
                found_windows.append(worker_window)

    win32gui.EnumWindows(enum_callback, None)

    if found_windows:
        return found_windows[0]
    worker_window = win32gui.FindWindowEx(progman, 0, "WorkerW", None)
    return worker_window or progman


def list_monitors():
    return [(int(m), rect) for m, _, rect in win32api.EnumDisplayMonitors()]


def is_window_cloaked_by_dwm(hwnd):
    cloaked = wintypes.DWORD(0)
    try:
        dwmapi.DwmGetWindowAttribute(
            wintypes.HWND(hwnd),
            DWMWA_CLOAKED,
            ctypes.byref(cloaked),
            ctypes.sizeof(cloaked),
        )
    except OSError:
        return False
    return cloaked.value != 0


def get_covered_monitors(ignore_hwnds):
    covered_monitors = set()

    def enum_callback(hwnd, _):
        try:
            if hwnd in ignore_hwnds:
                return
            if not win32gui.IsWindowVisible(hwnd) or win32gui.IsIconic(hwnd):
                return
            if win32gui.GetClassName(hwnd) in IGNORE_CLASSES:
                return
            if is_window_cloaked_by_dwm(hwnd):
                return

            ex_style = win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)
            if ex_style & win32con.WS_EX_TOOLWINDOW:
                return

            is_maximized = (
                win32gui.GetWindowPlacement(hwnd)[1] == win32con.SW_SHOWMAXIMIZED
            )

            monitor = win32api.MonitorFromWindow(hwnd, win32con.MONITOR_DEFAULTTONEAREST)
            left, top, right, bottom = win32api.GetMonitorInfo(monitor)["Monitor"]
            x1, y1, x2, y2 = win32gui.GetWindowRect(hwnd)
            is_fullscreen = x1 <= left and y1 <= top and x2 >= right and y2 >= bottom

            if is_maximized or is_fullscreen:
                covered_monitors.add(int(monitor))
                if DEBUG:
                    print(
                        f"[pause] {win32gui.GetClassName(hwnd)!r} - "
                        f"{win32gui.GetWindowText(hwnd)!r}"
                    )
        except Exception:
            pass

    win32gui.EnumWindows(enum_callback, None)
    return covered_monitors


# ----------------------------------------------------------------------------
# Wallpaper Instance per Monitor (mpv)
# ----------------------------------------------------------------------------
class MonitorWallpaper:
    def __init__(self, hmonitor, rect, workerw, video_path):
        self.hmonitor = hmonitor
        self.rect = rect
        self.workerw = workerw

        # Container widget where mpv renders the video
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
            loop_file="inf",        # Gapless loop
            mute="yes",
            hwdec="auto-safe",      # Hardware acceleration decoding
            vo="gpu",
            panscan=1.0,            # Fill screen by cropping overflowing borders
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
            self.hwnd,
            0,
            x,
            y,
            right - left,
            bottom - top,
            win32con.SWP_NOZORDER
            | win32con.SWP_NOACTIVATE
            | win32con.SWP_FRAMECHANGED
            | win32con.SWP_SHOWWINDOW,
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


# ----------------------------------------------------------------------------
# Controller (Tray icon + periodic monitor check)
# ----------------------------------------------------------------------------
class Controller:
    def __init__(self, app, video_path):
        self.app = app
        self.video_path = video_path
        self.manual_pause = False
        self.auto_pause = True

        workerw = find_workerw()
        self.wallpapers = [
            MonitorWallpaper(hmon, rect, workerw, video_path)
            for hmon, rect in list_monitors()
        ]
        self.own_hwnds = {w.hwnd for w in self.wallpapers}

        self._create_tray_icon()

        self.timer = QTimer()
        self.timer.timeout.connect(self.check_monitors)
        self.timer.start(CHECK_INTERVAL_MS)

    def _create_tray_icon(self):
        icon = self.app.style().standardIcon(QStyle.StandardPixmap.SP_MediaPlay)
        self.tray = QSystemTrayIcon(icon)
        self.tray.setToolTip("Video Wallpaper")

        menu = QMenu()

        self.pause_action = QAction("Pause", menu)
        self.pause_action.triggered.connect(self.toggle_manual_pause)
        menu.addAction(self.pause_action)

        self.auto_action = QAction("Pause automatically (maximized windows)", menu)
        self.auto_action.setCheckable(True)
        self.auto_action.setChecked(True)
        self.auto_action.toggled.connect(self.toggle_auto_pause)
        menu.addAction(self.auto_action)

        change_action = QAction("Change video...", menu)
        change_action.triggered.connect(self.change_video)
        menu.addAction(change_action)

        menu.addSeparator()

        exit_action = QAction("Exit", menu)
        exit_action.triggered.connect(self.exit_app)
        menu.addAction(exit_action)

        self.menu = menu
        self.tray.setContextMenu(menu)
        self.tray.show()

    def toggle_manual_pause(self):
        self.manual_pause = not self.manual_pause
        self.pause_action.setText("Resume" if self.manual_pause else "Pause")
        self.check_monitors()

    def toggle_auto_pause(self, enabled):
        self.auto_pause = enabled
        self.check_monitors()

    def change_video(self):
        video_path, _ = QFileDialog.getOpenFileName(
            None, "Select Video", "", "Videos (*.mp4 *.mkv *.webm *.avi *.mov)"
        )
        if not video_path:
            return
        self.video_path = video_path
        save_video_path(video_path)
        for w in self.wallpapers:
            w.set_video(video_path)

    def exit_app(self):
        self.timer.stop()
        for w in self.wallpapers:
            w.close()
        self.tray.hide()
        self.app.quit()

    def check_monitors(self):
        covered = get_covered_monitors(self.own_hwnds) if self.auto_pause else set()
        for w in self.wallpapers:
            should_pause = self.manual_pause or (w.hmonitor in covered)
            w.set_pause(should_pause)


# ----------------------------------------------------------------------------
# Main entry point
# ----------------------------------------------------------------------------
def main():
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    # python-mpv requires LC_NUMERIC to be set to "C" (Qt can override this)
    locale.setlocale(locale.LC_NUMERIC, "C")

    video_path = sys.argv[1] if len(sys.argv) > 1 else load_video_path()

    if not video_path or not os.path.isfile(video_path):
        video_path, _ = QFileDialog.getOpenFileName(
            None, "Select Video", "", "Videos (*.mp4 *.mkv *.webm *.avi *.mov)"
        )
        if not video_path:
            return

    save_video_path(video_path)

    controller = Controller(app, video_path)  # noqa: F841
    sys.exit(app.exec())


if __name__ == "__main__":
    main()