import os
import sys
from ai.EXPManager import exp_manager
import keyboard
import qtawesome as qta
from PyQt6.QtCore import Qt, QTimer, QSize, pyqtSignal
from PyQt6.QtGui import QFontDatabase, QPixmap, QPainter, QPainterPath, QColor, QPen
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QFrame, QProgressBar, QStackedWidget
)

from ai.MoodController import mood
import ui.Theme as Theme

from ui.ChatHistoryPage import ChatHistoryPage
from ui.PreferencesPage import PreferencesPage

MOOD_REFRESH_INTERVAL_MS = 2000

TAB_HISTORY = 0
TAB_SETTINGS = 1
TAB_PREFERENCES = 2

ASSETS_DIR = os.path.join(os.path.dirname(__file__), "assets")
OXANIUM_FONT_PATH = os.path.join(ASSETS_DIR, "Oxanium-VariableFont_wght.ttf")

MOOD_IMAGE_MAP = {
    "ANGER": "venus_angry.png",
    "BORED": "venus_bored.png",
    "TIRED": "venus_tired.png",
    "POUTY": "venus_pouty.png",
    "NORMAL": "venus_profile.png",
}

_oxanium_family = None


def _load_oxanium_family():
    global _oxanium_family
    if _oxanium_family is not None:
        return _oxanium_family

    font_id = QFontDatabase.addApplicationFont(OXANIUM_FONT_PATH)
    families = QFontDatabase.applicationFontFamilies(font_id) if font_id != -1 else []
    _oxanium_family = families[0] if families else "Segoe UI"
    return _oxanium_family


class DraggableFrame(QFrame):
    def __init__(self):
        super().__init__()
        self._drag_offset = None

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_offset = (
                event.globalPosition().toPoint() - self.window().frameGeometry().topLeft()
            )
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag_offset is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.window().move(event.globalPosition().toPoint() - self._drag_offset)
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._drag_offset = None
        super().mouseReleaseEvent(event)


class NavButton(QPushButton):
    def __init__(self, icon_name, label, active=False):
        super().__init__(f"  {label}                                   >")
        self.icon_name = icon_name
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(64)
        self._hovered = False
        self.set_active(active)
        Theme.theme_signals.changed.connect(self._on_theme_changed)

    def set_active(self, active):
        self._active = active
        self._update_icon_color()
        self._apply_style()

    def _on_theme_changed(self):
        self._update_icon_color(hovered=self._hovered)
        self._apply_style()

    def _update_icon_color(self, hovered=False):
        self._hovered = hovered
        icon_color = "white" if (self._active or hovered) else Theme.PINK_SOFT
        self.setIcon(qta.icon(self.icon_name, color=icon_color))
        self.setIconSize(QSize(20, 20))

    def enterEvent(self, event):
        if not self._active:
            self._update_icon_color(hovered=True)
        super().enterEvent(event)

    def leaveEvent(self, event):
        if not self._active:
            self._update_icon_color(hovered=False)
        super().leaveEvent(event)

    def _apply_style(self):
        if self._active:
            self.setStyleSheet(f"""
                QPushButton {{
                    text-align: left;
                    padding-left: 18px;
                    background-color: {Theme.BG_BUBBLE};
                    color: white;
                    border: 1px solid {Theme.PINK};
                    border-radius: 12px;
                    font-size: 18px;
                }}
            """)
        else:
            self.setStyleSheet(f"""
                QPushButton {{
                    text-align: left;
                    padding-left: 18px;
                    background-color: #16051a;
                    color: {Theme.PINK_SOFT};
                    border: none;
                    font-size: 18px;
                }}
                QPushButton:hover {{
                    color: white;
                }}
            """)


class AvatarCircle(QLabel):
    """Round avatar widget supporting image files with fallback initials."""

    def __init__(self, image_path=None, initials="V"):
        super().__init__()
        self.setFixedSize(78, 78)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.initials = initials
        self._current_image_path = None
        self.set_image(image_path)
        Theme.theme_signals.changed.connect(self._on_theme_changed)

    def _on_theme_changed(self):
        # Re-render so the border color (image mode) or fallback style updates.
        self.set_image(self._current_image_path)

    def set_image(self, image_path):
        self._current_image_path = image_path

        if image_path and os.path.exists(image_path):
            pixmap = QPixmap(image_path)
            if not pixmap.isNull():
                self.setPixmap(self._make_circular_pixmap(pixmap, 78, border_width=2))
                self.setStyleSheet("background: transparent; border: none;")
                return

        # Fallback if image path is invalid or missing
        self.setText(self.initials)
        self.setStyleSheet(f"""
            background-color: {Theme.BG_BUBBLE};
            border: 2px solid {Theme.PINK};
            border-radius: 39px;
            color: {Theme.PINK};
            font-size: 24px;
            font-weight: bold;
        """)

    def _make_circular_pixmap(self, src_pixmap, size, border_width=2):
        scaled = src_pixmap.scaled(
            size, size,
            Qt.AspectRatioMode.KeepAspectRatioByExpanding,
            Qt.TransformationMode.SmoothTransformation
        )

        dest = QPixmap(size, size)
        dest.fill(Qt.GlobalColor.transparent)

        painter = QPainter(dest)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # 1. Clip and draw image
        path = QPainterPath()
        path.addEllipse(0, 0, size, size)
        painter.setClipPath(path)

        x = (size - scaled.width()) // 2
        y = (size - scaled.height()) // 2
        painter.drawPixmap(x, y, scaled)

        # 2. Reset clip to draw smooth border over edges
        painter.setClipping(False)

        # 3. Draw pixel-perfect anti-aliased border
        pen = QPen(QColor(Theme.PINK))
        pen.setWidth(border_width)
        painter.setPen(pen)

        half_pen = border_width / 2.0
        painter.drawEllipse(
            int(half_pen),
            int(half_pen),
            size - border_width,
            size - border_width
        )

        painter.end()
        return dest


class MoodStatBar(QWidget):
    def __init__(self, icon_name, label):
        super().__init__()
        self.icon_name = icon_name
        self.label_text = label

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 8, 6, 8)
        layout.setSpacing(4)
        layout.setAlignment(Qt.AlignmentFlag.AlignHCenter)

        self.icon_label = QLabel()
        self.icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.icon_label.setStyleSheet("border: none; background: transparent;")

        self.name_label = QLabel(label)
        self.name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.bar = QProgressBar()
        self.bar.setOrientation(Qt.Orientation.Vertical)
        self.bar.setRange(0, 100)
        self.bar.setTextVisible(False)
        self.bar.setFixedSize(18, 92)

        self.percent_label = QLabel("0%")
        self.percent_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        layout.addWidget(self.icon_label)
        layout.addWidget(self.name_label)
        layout.addWidget(self.bar, alignment=Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(self.percent_label)

        self._apply_style()
        Theme.theme_signals.changed.connect(self._apply_style)

    def _apply_style(self):
        self.setStyleSheet("""
            QWidget {
                background-color: #18051b;
                border-radius: 10px;
            }
        """)
        self.icon_label.setPixmap(qta.icon(self.icon_name, color=Theme.PINK).pixmap(QSize(18, 18)))
        self.name_label.setStyleSheet(
            f"color: {Theme.PINK_SOFT}; font-size: 8px; border: none; background: transparent;")
        self.bar.setStyleSheet(f"""
            QProgressBar {{
                background-color: {Theme.BG_BUBBLE};
                border: 1px solid {Theme.PINK};
                border-radius: 7px;
            }}
            QProgressBar::chunk {{
                background-color: {Theme.PINK};
                border-radius: 5px;
            }}
        """)
        self.percent_label.setStyleSheet(
            f"color: {Theme.PINK_SOFT}; font-size: 11px; border: none; background: transparent;")

    def set_value(self, value):
        value = max(0, min(100, int(value)))
        self.bar.setValue(value)
        self.percent_label.setText(f"{value}%")


class PlaceholderPage(QWidget):
    def __init__(self, title):
        super().__init__()

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.label = QLabel(f"{title} — coming soon")
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.label)

        self._apply_style()
        Theme.theme_signals.changed.connect(self._apply_style)

    def _apply_style(self):
        self.label.setStyleSheet(
            f"color: {Theme.PINK_SOFT}; font-size: 20px; border: none; background: transparent;")


class PanelWindow(QWidget):

    toggle_requested = pyqtSignal()

    def __init__(self, process_question):
        super().__init__()

        self.process_question = process_question
        self.font_family = _load_oxanium_family()
        self.nav_buttons = []

        self.setWindowTitle("Venus Panel")
        self.setWindowFlags(
            Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.resize(950, 560)

        self.toggle_requested.connect(self.toggle)

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(14)

        self._sidebar_frame = self._build_sidebar()
        root.addWidget(self._sidebar_frame)
        root.addWidget(self._build_main_area(), stretch=1)

        self._apply_window_style()
        Theme.theme_signals.changed.connect(self._on_theme_changed)

        self._mood_timer = QTimer(self)
        self._mood_timer.timeout.connect(self._refresh_mood)
        self._mood_timer.start(MOOD_REFRESH_INTERVAL_MS)
        self._refresh_mood()

    def _on_theme_changed(self):
        # Widgets with their own theme listeners (NavButton, AvatarCircle,
        # MoodStatBar, PlaceholderPage) repaint themselves. Anything styled
        # directly here needs a manual refresh.
        self._apply_window_style()
        self._apply_sidebar_style()
        self._apply_profile_container_style()
        self._apply_divider_style()
        self._apply_heart_icon()
        self._apply_xp_bar_style()
        self._apply_close_button_style()

    def _apply_window_style(self):
        self.setStyleSheet(f"""
            QWidget {{
                background-color: {Theme.BG_DARK};
                color: white;
                font-family: "{self.font_family}";
            }}
            QScrollBar:vertical {{
                background: #16051a;
                width: 12px;
                margin: 4px;
            }}
            QScrollBar::handle:vertical {{
                background: {Theme.PINK};
                border-radius: 6px;
                min-height: 28px;
            }}
            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical {{
                height: 0px;
            }}
        """)

    def _apply_sidebar_style(self):
        self._sidebar_frame.setStyleSheet(f"""
            QFrame {{
                background-color: {Theme.BG_PANEL};
                border: none;
                border-radius: 18px;
            }}
        """)

    def _apply_profile_container_style(self):
        self._profile_container.setStyleSheet(f"""
            QFrame {{
                background-color: {Theme.BG_BUBBLE};
                border: none;
                border-radius: 14px;
            }}
        """)

    def _apply_divider_style(self):
        self._divider.setStyleSheet(f"background-color: {Theme.PINK}; border: none;")

    def _apply_heart_icon(self):
        self._sidebar_heart.setPixmap(qta.icon("fa5s.heart", color=Theme.PINK).pixmap(QSize(22, 22)))
        self._name_heart.setPixmap(qta.icon("fa5s.heart", color=Theme.PINK).pixmap(QSize(13, 13)))

    def _apply_xp_bar_style(self):
        self.xp_bar.setStyleSheet(f"""
            QProgressBar {{
                background-color: #16051a;
                border: none;
                border-radius: 5px;
            }}
            QProgressBar::chunk {{
                background-color: {Theme.PINK};
                border-radius: 5px;
            }}
        """)
        self._xp_caption.setStyleSheet(
            f"color: {Theme.PINK_SOFT}; font-size: 11px; border: none; background: transparent;")
        self.xp_value_label.setStyleSheet(
            f"color: {Theme.PINK_SOFT}; font-size: 11px; border: none; background: transparent;")
        self.level_label.setStyleSheet(
            f"color: {Theme.PINK_SOFT}; font-size: 11px; border: none; background: transparent;")

    def _apply_close_button_style(self):
        self._close_button.setIcon(qta.icon("fa5s.times", color=Theme.PINK_SOFT, color_active="white"))
        self._close_button.setStyleSheet(f"""
            QPushButton {{
                background-color: #16051a;
                border: 1px solid {Theme.PINK};
                border-radius: 10px;
                color: {Theme.PINK_SOFT};
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {Theme.PINK};
                color: white;
            }}
        """)

    def _build_sidebar(self):
        sidebar = DraggableFrame()
        sidebar.setFixedWidth(240)

        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(16, 20, 16, 16)
        layout.setSpacing(14)

        history_button = NavButton("fa5s.comment", "Chat", active=True)
        settings_button = NavButton("fa5s.cog", "Settings")
        preferences_button = NavButton("fa5s.sliders-h", "Preferences")

        history_button.clicked.connect(lambda: self._switch_tab(TAB_HISTORY))
        settings_button.clicked.connect(lambda: self._switch_tab(TAB_SETTINGS))
        preferences_button.clicked.connect(lambda: self._switch_tab(TAB_PREFERENCES))

        self.nav_buttons = [history_button, settings_button, preferences_button]

        layout.addWidget(history_button)
        layout.addWidget(settings_button)
        layout.addWidget(preferences_button)

        self._divider = QFrame()
        self._divider.setFixedHeight(1)
        layout.addSpacing(4)
        layout.addWidget(self._divider)

        layout.addWidget(self._build_profile_section())
        layout.addStretch()

        self._sidebar_heart = QLabel()
        self._sidebar_heart.setStyleSheet("border: none; background: transparent;")
        layout.addWidget(self._sidebar_heart, alignment=Qt.AlignmentFlag.AlignLeft)

        return sidebar

    def _switch_tab(self, index):
        self.content_stack.setCurrentIndex(index)
        for button_index, button in enumerate(self.nav_buttons):
            button.set_active(button_index == index)

    def set_avatar_mood(self, mood_state):
        """Swap the sidebar avatar image based on a mood state string.

        mood_state: one of "ANGER", "BORED", "TIRED", "POUTY", "NORMAL"
        (case-insensitive). Falls back to the normal image on an
        unrecognized value.
        """
        filename = MOOD_IMAGE_MAP.get(mood_state.upper(), "venus_profile.png")
        image_path = os.path.join(ASSETS_DIR, filename)
        self.avatar.set_image(image_path)

    def _build_profile_section(self):
        self._profile_container = QFrame()
        layout = QVBoxLayout(self._profile_container)
        layout.setContentsMargins(12, 14, 12, 12)
        layout.setSpacing(10)

        profile_image_path = os.path.join(ASSETS_DIR, "venus_profile.png")

        header = QHBoxLayout()
        header.setSpacing(10)
        self.avatar = AvatarCircle(image_path=profile_image_path, initials="V")
        header.addWidget(self.avatar)

        name_column = QVBoxLayout()
        name_column.setSpacing(2)

        name_row = QHBoxLayout()
        name_row.setSpacing(6)
        name_label = QLabel("Venus")
        name_label.setStyleSheet(
            "color: white; font-size: 16px; font-weight: bold; border: none; background: transparent;")
        self._name_heart = QLabel()
        self._name_heart.setStyleSheet("border: none; background: transparent;")
        name_row.addWidget(name_label)
        name_row.addWidget(self._name_heart)
        name_row.addStretch()

        self.level_label = QLabel("Lv. —")

        name_column.addLayout(name_row)
        name_column.addWidget(self.level_label)

        header.addLayout(name_column)
        header.addStretch()
        layout.addLayout(header)

        xp_row = QHBoxLayout()
        self._xp_caption = QLabel("XP")
        self.xp_value_label = QLabel("— / —")
        xp_row.addWidget(self._xp_caption)
        xp_row.addStretch()
        xp_row.addWidget(self.xp_value_label)
        layout.addLayout(xp_row)

        self.xp_bar = QProgressBar()
        self.xp_bar.setRange(0, 100)
        self.xp_bar.setValue(0)
        self.xp_bar.setTextVisible(False)
        self.xp_bar.setFixedHeight(10)
        layout.addWidget(self.xp_bar)

        stats_row = QHBoxLayout()
        stats_row.setSpacing(6)

        self.anger_bar = MoodStatBar("fa5s.angry", "Anger")
        self.energy_bar = MoodStatBar("fa5s.bolt", "Energy")
        self.boredom_bar = MoodStatBar("fa5s.tired", "Boredom")
        self.affection_bar = MoodStatBar("fa5s.heart", "Affection")

        for stat_bar in (self.anger_bar, self.energy_bar, self.boredom_bar, self.affection_bar):
            stats_row.addWidget(stat_bar)

        layout.addLayout(stats_row)

        # Apply colors now that all the widgets referenced by _on_theme_changed exist.
        self._apply_profile_container_style()
        self._apply_heart_icon()
        self._apply_xp_bar_style()

        return self._profile_container

    def _refresh_mood(self):
        self.anger_bar.set_value(mood.anger)
        self.energy_bar.set_value(mood.energy)
        self.boredom_bar.set_value(mood.boredom)
        self.affection_bar.set_value(mood.affection)
        self._refresh_exp()

    def _refresh_exp(self):
        current_xp, xp_needed = exp_manager.progress()
        self.level_label.setText(f"Lv. {exp_manager.level}")
        self.xp_value_label.setText(f"{current_xp} / {xp_needed}")
        percent = int(100 * current_xp / xp_needed) if xp_needed else 0
        self.xp_bar.setValue(max(0, min(100, percent)))

    def _build_main_area(self):
        container = DraggableFrame()
        container.setObjectName("mainArea")

        container.setStyleSheet("""
            #mainArea {
                background-color: #080108;
            }
        """)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(20, 16, 20, 20)
        layout.setSpacing(14)

        layout.addLayout(self._build_header())

        self.content_stack = QStackedWidget()
        self.content_stack.addWidget(ChatHistoryPage(self.process_question))
        self.content_stack.addWidget(PlaceholderPage("Settings"))
        self.content_stack.addWidget(PreferencesPage())
        layout.addWidget(self.content_stack, stretch=1)

        return container

    def _build_header(self):
        header = QHBoxLayout()
        header.addStretch()

        self._close_button = QPushButton()
        self._close_button.setIconSize(QSize(16, 16))
        self._close_button.setFixedSize(32, 32)
        self._close_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._close_button.clicked.connect(self.hide)
        header.addWidget(self._close_button)

        self._apply_close_button_style()

        return header

    def toggle(self):
        if self.isVisible():
            self.hide()
        else:
            self.show()
            self.raise_()
            self.activateWindow()


def start_panel_window(process_question, hotkey="ctrl+alt+h"):
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    window = PanelWindow(process_question)
    keyboard.add_hotkey(hotkey, window.toggle_requested.emit)
    print(f"[PanelWindow] Hotkey '{hotkey}' registered globally.")

    sys.exit(app.exec())