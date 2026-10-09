import locale
import os
import threading
import time
from pathlib import Path

import qtawesome as qta
from PyQt6.QtCore import Qt, QSize, QObject, QRectF, pyqtSignal
from PyQt6.QtGui import QImage, QPixmap, QPainter, QPainterPath
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel,
    QPushButton, QFrame, QScrollArea, QFileDialog
)

from ui.PreferencesPage import ToggleSwitch
from ai.WallpaperManager import wallpaper_manager
from ai.WallpaperStore import wallpaper_store
import ui.Theme as Theme

GRID_COLUMNS = 4
VIDEO_FILE_FILTER = "Videos (*.mp4 *.mkv *.webm *.avi *.mov)"
THUMBNAIL_WIDTH = 400
THUMBNAIL_FRAME_POSITION = 0.1  # grab the frame at 10% of the video, not the (often black) first one
MPV_LOAD_TIMEOUT_SECONDS = 8


def _extract_frame_opencv(path):
    try:
        import cv2
    except ImportError:
        print("[Thumbnails] opencv-python-headless is not installed (pip install opencv-python-headless).")
        return None

    try:
        capture = cv2.VideoCapture(path)
        if not capture.isOpened():
            print(f"[Thumbnails] OpenCV couldn't open '{path}' (unsupported codec or path?).")
            return None

        total_frames = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
        if total_frames > 0:
            capture.set(cv2.CAP_PROP_POS_FRAMES, int(total_frames * THUMBNAIL_FRAME_POSITION))

        success, frame = capture.read()
        capture.release()

        if not success:
            print(f"[Thumbnails] OpenCV couldn't decode a frame from '{path}'.")
            return None

        height, width = frame.shape[:2]
        new_height = max(1, int(height * THUMBNAIL_WIDTH / width))
        frame = cv2.resize(frame, (THUMBNAIL_WIDTH, new_height))
        frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

        height, width = frame.shape[:2]
        return QImage(frame.data, width, height, 3 * width, QImage.Format.Format_RGB888).copy()

    except Exception:
        import traceback
        traceback.print_exc()
        return None


def _extract_frame_mpv(path):
    """Fallback: same decoder the wallpaper itself uses, so if it plays, this works."""
    try:
        import mpv

        # python-mpv requires LC_NUMERIC "C", and Qt can override it.
        locale.setlocale(locale.LC_NUMERIC, "C")

        player = mpv.MPV(
            vo="null", ao="null", mute="yes", hr_seek="yes", hwdec="no",
            osc="no", input_default_bindings="no", input_vo_keyboard="no",
        )
    except Exception as error:
        print(f"[Thumbnails] mpv fallback unavailable: {error}")
        return None

    try:
        player.play(path)

        duration = None
        deadline = time.time() + MPV_LOAD_TIMEOUT_SECONDS
        while time.time() < deadline:
            try:
                duration = player.duration
            except Exception:
                duration = None
            if duration:
                break
            time.sleep(0.1)

        if not duration:
            print(f"[Thumbnails] mpv couldn't load '{path}' in time.")
            return None

        player.seek(duration * THUMBNAIL_FRAME_POSITION, reference="absolute", precision="exact")
        player.pause = True
        time.sleep(0.6)

        pil_image = player.screenshot_raw()
        if pil_image is None:
            print(f"[Thumbnails] mpv returned no frame for '{path}'.")
            return None

        pil_image = pil_image.convert("RGB")
        pil_image.thumbnail((THUMBNAIL_WIDTH, THUMBNAIL_WIDTH * 4))

        data = pil_image.tobytes()
        width, height = pil_image.size
        return QImage(data, width, height, 3 * width, QImage.Format.Format_RGB888).copy()

    except Exception:
        import traceback
        traceback.print_exc()
        return None

    finally:
        try:
            player.terminate()
        except Exception:
            pass


def _extract_frame(path):
    return _extract_frame_opencv(path) or _extract_frame_mpv(path)


class _ThumbnailLoader(QObject):
    """
    Loads a video's cached thumbnail from disk, or extracts one (OpenCV,
    then mpv) and saves it, on background threads (two at a time).
    Emits `ready(path, QImage)` back on the Qt main thread. Also keeps
    an in-memory cache so the grid rebuilding doesn't touch the disk.
    """

    ready = pyqtSignal(str, QImage)

    def __init__(self):
        super().__init__()
        self._cache = {}
        self._pending = set()
        self._failed = set()
        self._lock = threading.Lock()
        self._slots = threading.Semaphore(2)

    def request(self, path):
        with self._lock:
            cached = self._cache.get(path)
            if cached is None:
                if path in self._pending or path in self._failed:
                    return
                self._pending.add(path)

        if cached is not None:
            self.ready.emit(path, cached)
            return

        threading.Thread(target=self._work, args=(path,), daemon=True).start()

    def _work(self, path):
        with self._slots:
            image = self._load_or_create(path)

        with self._lock:
            self._pending.discard(path)
            if image is None:
                self._failed.add(path)
            else:
                self._cache[path] = image

        if image is not None:
            self.ready.emit(path, image)

    def _load_or_create(self, path):
        thumb_path = wallpaper_store.thumbnail_path(path)

        if thumb_path.is_file():
            image = QImage(str(thumb_path))
            if not image.isNull():
                return image

        image = _extract_frame(path)

        if image is not None:
            image.save(str(thumb_path), "JPG", 85)

        return image


thumbnail_loader = _ThumbnailLoader()


class _ThumbnailLabel(QLabel):
    """Shows the placeholder icon until set_cover() is called, then paints the frame cropped to fill."""

    def __init__(self):
        super().__init__()
        self._cover = None

    def set_cover(self, pixmap):
        self._cover = pixmap
        self.update()

    def paintEvent(self, event):
        if self._cover is None:
            super().paintEvent(event)
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        clip = QPainterPath()
        clip.addRoundedRect(QRectF(self.rect()), 8, 8)
        painter.setClipPath(clip)

        scaled = self._cover.scaled(
            self.size(),
            Qt.AspectRatioMode.KeepAspectRatioByExpanding,
            Qt.TransformationMode.SmoothTransformation,
        )
        x = (self.width() - scaled.width()) // 2
        y = (self.height() - scaled.height()) // 2
        painter.drawPixmap(x, y, scaled)
        painter.end()


class WallpaperCard(QFrame):

    clicked = pyqtSignal(str)

    def __init__(self, path):
        super().__init__()
        self.setObjectName("wallpaperCard")
        self.path = path
        self.setToolTip(path)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        self.thumbnail = _ThumbnailLabel()
        self.thumbnail.setFixedHeight(110)
        self.thumbnail.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.thumbnail)

        bottom = QHBoxLayout()
        self.name_label = QLabel(os.path.basename(path))
        self.delete_button = QPushButton()
        self.delete_button.setFixedSize(24, 24)
        self.delete_button.setIconSize(QSize(14, 14))
        self.delete_button.setCursor(Qt.CursorShape.PointingHandCursor)

        bottom.addWidget(self.name_label, stretch=1)
        bottom.addWidget(self.delete_button)
        layout.addLayout(bottom)

        self._apply_style()
        Theme.theme_signals.changed.connect(self._apply_style)

        thumbnail_loader.ready.connect(self._on_thumbnail_ready)
        thumbnail_loader.request(path)

    def _on_thumbnail_ready(self, path, image):
        if path != self.path:
            return

        self.thumbnail.set_cover(QPixmap.fromImage(image))

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.path)
            event.accept()
            return

        super().mousePressEvent(event)

    def _apply_style(self):
        self.setStyleSheet("""
            #wallpaperCard {
                background-color: #18051b;
                border-radius: 12px;
            }
        """)
        self.thumbnail.setPixmap(qta.icon("fa5s.image", color=Theme.PINK_SOFT).pixmap(QSize(32, 32)))
        self.thumbnail.setStyleSheet(
            f"background-color: {Theme.BG_BUBBLE}; border: none; border-radius: 8px;")
        self.name_label.setStyleSheet(
            "color: white; font-size: 13px; border: none; background: transparent;")
        self.delete_button.setIcon(qta.icon("fa5s.trash-alt", color=Theme.PINK_SOFT, color_active="white"))
        self.delete_button.setStyleSheet("""
            QPushButton { background: transparent; border: none; }
        """)


class WallpaperPage(QWidget):

    # Emitted from the copy thread, handled on the main thread.
    file_copied = pyqtSignal(str)
    import_finished = pyqtSignal()

    def __init__(self):
        super().__init__()

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(14)

        outer.addLayout(self._build_header())

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(14)

        content_layout.addWidget(self._build_management_row())
        content_layout.addWidget(self._build_import_button())
        content_layout.addLayout(self._build_list_header())

        self.grid = QGridLayout()
        self.grid.setSpacing(12)
        for column in range(GRID_COLUMNS):
            self.grid.setColumnStretch(column, 1)
        content_layout.addLayout(self.grid)
        content_layout.addStretch()

        scroll.setWidget(content)
        outer.addWidget(scroll, stretch=1)

        self.file_copied.connect(wallpaper_store.add)
        self.import_finished.connect(self._on_import_finished)

        self._apply_style()
        Theme.theme_signals.changed.connect(self._apply_style)

        self.refresh()
        wallpaper_store.subscribe(self.refresh)

    # ------------------------------------------------------------------
    # Sections
    # ------------------------------------------------------------------

    def _build_header(self):
        header = QHBoxLayout()
        header.setSpacing(10)

        self._header_icon = QLabel()
        self._header_title = QLabel("Wallpaper")

        header.addWidget(self._header_icon)
        header.addWidget(self._header_title)
        header.addStretch()
        return header

    def _build_management_row(self):
        self._management_frame = QFrame()
        self._management_frame.setObjectName("managementRow")

        layout = QHBoxLayout(self._management_frame)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(16)

        self._management_icon = QLabel()
        layout.addWidget(self._management_icon)

        text_column = QVBoxLayout()
        text_column.setSpacing(4)
        self._management_title = QLabel("Wallpaper Management")
        self._management_description = QLabel(
            "Automatically change your wallpaper at set intervals or based on events.")
        self._management_description.setWordWrap(True)
        text_column.addWidget(self._management_title)
        text_column.addWidget(self._management_description)
        layout.addLayout(text_column, stretch=1)

        self.management_toggle = ToggleSwitch(checked=False)
        layout.addWidget(self.management_toggle)

        return self._management_frame

    def _build_import_button(self):
        self.import_button = QPushButton("  Import Image")
        self.import_button.setFixedHeight(56)
        self.import_button.setIconSize(QSize(20, 20))
        self.import_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.import_button.clicked.connect(self._open_import_dialog)
        return self.import_button

    def _build_list_header(self):
        row = QHBoxLayout()

        self._list_title = QLabel("Imported Wallpapers")
        row.addWidget(self._list_title)
        row.addStretch()

        self.grid_button = QPushButton()
        self.list_button = QPushButton()
        for button in (self.grid_button, self.list_button):
            button.setFixedSize(36, 36)
            button.setIconSize(QSize(16, 16))
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            row.addWidget(button)

        return row

    # ------------------------------------------------------------------
    # Import / apply
    # ------------------------------------------------------------------

    def _open_import_dialog(self):
        videos_dir = Path.home() / "Videos"
        start_dir = str(videos_dir) if videos_dir.is_dir() else ""

        paths, _ = QFileDialog.getOpenFileNames(
            self, "Import wallpaper videos", start_dir, VIDEO_FILE_FILTER
        )

        if not paths:
            return

        self.import_button.setEnabled(False)
        self.import_button.setText("  Importing...")

        threading.Thread(target=self._copy_worker, args=(paths,), daemon=True).start()

    def _copy_worker(self, paths):
        try:
            for path in paths:
                try:
                    name = wallpaper_store.copy_into_library(path)
                except OSError as error:
                    print(f"[WallpaperPage] Failed to copy '{path}': {error}")
                    continue

                self.file_copied.emit(name)
        finally:
            self.import_finished.emit()

    def _on_import_finished(self):
        self.import_button.setEnabled(True)
        self.import_button.setText("  Import Image")

    def _apply_wallpaper(self, path):
        wallpaper_manager.play(path)

    # ------------------------------------------------------------------
    # List rendering
    # ------------------------------------------------------------------

    def refresh(self):
        while self.grid.count():
            item = self.grid.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        videos = wallpaper_store.get_all()

        if not videos:
            self._empty_label = QLabel("No wallpapers imported yet")
            self._empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._empty_label.setStyleSheet(
                f"color: {Theme.PINK_SOFT}; font-size: 13px; border: none; background: transparent;")
            self.grid.addWidget(self._empty_label, 0, 0, 1, GRID_COLUMNS)
            return

        for index, path in enumerate(videos):
            card = WallpaperCard(path)
            card.clicked.connect(self._apply_wallpaper)
            self.grid.addWidget(card, index // GRID_COLUMNS, index % GRID_COLUMNS)

    # ------------------------------------------------------------------
    # Theming
    # ------------------------------------------------------------------

    def _apply_style(self):
        self._header_icon.setPixmap(qta.icon("fa5s.image", color=Theme.PINK).pixmap(QSize(30, 30)))
        self._header_icon.setStyleSheet("border: none; background: transparent;")
        self._header_title.setStyleSheet(
            f"color: {Theme.PINK}; font-size: 24px; font-weight: bold; border: none; background: transparent;")

        self._management_frame.setStyleSheet("""
            #managementRow {
                background-color: #18051b;
                border-radius: 12px;
            }
        """)
        self._management_icon.setPixmap(qta.icon("fa5s.image", color=Theme.PINK).pixmap(QSize(36, 36)))
        self._management_icon.setStyleSheet("border: none; background: transparent;")
        self._management_title.setStyleSheet(
            "color: white; font-size: 16px; font-weight: bold; border: none; background: transparent;")
        self._management_description.setStyleSheet(
            f"color: {Theme.PINK_SOFT}; font-size: 12px; border: none; background: transparent;")

        self.import_button.setIcon(qta.icon("fa5s.upload", color=Theme.PINK))
        self.import_button.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                border: 2px solid {Theme.PINK};
                border-radius: 12px;
                color: {Theme.PINK};
                font-size: 16px;
                font-weight: bold;
            }}
            QPushButton:hover {{ background-color: {Theme.BG_BUBBLE}; }}
            QPushButton:disabled {{ color: #666; border-color: #555; }}
        """)

        self._list_title.setStyleSheet(
            f"color: {Theme.PINK}; font-size: 16px; font-weight: bold; border: none; background: transparent;")

        self.grid_button.setIcon(qta.icon("fa5s.th-large", color=Theme.PINK))
        self.list_button.setIcon(qta.icon("fa5s.list", color=Theme.PINK_SOFT))

        self.grid_button.setStyleSheet(f"""
            QPushButton {{
                background-color: {Theme.BG_BUBBLE};
                border: 1px solid {Theme.PINK};
                border-radius: 8px;
            }}
        """)
        self.list_button.setStyleSheet("""
            QPushButton { background: transparent; border: none; }
        """)