import os
import sys

import keyboard
import qtawesome as qta
from PyQt6.QtCore import Qt, QTimer, QSize, pyqtSignal, QObject
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QFrame, QStackedWidget
)

from ai.EXPManager import exp_manager
from ai.MoodController import mood
import ui.Theme as Theme
from ui.ChatHistoryPage import ChatHistoryPage
from ui.PreferencesPage import PreferencesPage
from ui.SettingsPage import SettingsPage
from ui.ChatHistoryPage import ChatHistoryPage
from ui.PreferencesPage import PreferencesPage
from ui.NavButton import NavButton
from ui.ProfileSection import ProfileSection
from ui.PlaceholderPage import PlaceholderPage
from ui.Constants import (
    ASSETS_DIR,
    MOOD_IMAGE_MAP,
    MOOD_REFRESH_INTERVAL_MS,
    TAB_HISTORY,
    TAB_SETTINGS,
    TAB_PREFERENCES,
    load_oxanium_family,
)


class _AvatarSignals(QObject):
    mood_changed = pyqtSignal(str)


# Cross-thread bridge for set_avatar_mood(): Orchestrator's worker
# thread can't touch PanelWindow's QLabel/QPixmap directly, so
# Server.py emits this instead of calling the method — same pattern
# as Theme.theme_signals.
avatar_signals = _AvatarSignals()


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


class PanelWindow(QWidget):

    toggle_requested = pyqtSignal()

    def __init__(self, process_question):
        super().__init__()

        self.process_question = process_question
        self.font_family = load_oxanium_family()
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
        avatar_signals.mood_changed.connect(self.set_avatar_mood)

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(4)

        self._sidebar_frame = self._build_sidebar()
        root.addWidget(self._sidebar_frame)
        root.addWidget(self._build_main_area(), stretch=1)

        # Apply every theme-dependent style owned directly by this window,
        # once, now that sidebar and main area both exist. Sub-widgets
        # (NavButton, ProfileSection, PlaceholderPage) style themselves in
        # their own constructors — this only covers what PanelWindow itself
        # styles (window, sidebar frame, divider, sidebar heart, close
        # button). Previously the sidebar frame and divider were only ever
        # styled on a later theme change, leaving them unstyled at startup.
        Theme.theme_signals.changed.connect(self._on_theme_changed)
        self._on_theme_changed()

        self._mood_timer = QTimer(self)
        self._mood_timer.timeout.connect(self._refresh_mood)
        self._mood_timer.start(MOOD_REFRESH_INTERVAL_MS)
        self._refresh_mood()

    def _on_theme_changed(self):
        self._apply_window_style()
        self._apply_sidebar_style()
        self._apply_divider_style()
        self._apply_heart_icon()
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

    def _apply_divider_style(self):
        self._divider.setStyleSheet(f"background-color: {Theme.PINK}; border: none;")

    def _apply_heart_icon(self):
        self._sidebar_heart.setPixmap(qta.icon("fa5s.heart", color=Theme.PINK).pixmap(QSize(22, 22)))

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

        # Created before addWidget(profile_section) below — _on_theme_changed
        # needs this to exist, and its layout position (after the stretch)
        # is set by addWidget() order, not by when the widget was created.
        self._sidebar_heart = QLabel()
        self._sidebar_heart.setStyleSheet("border: none; background: transparent;")

        self.profile_section = ProfileSection(ASSETS_DIR)
        layout.addWidget(self.profile_section)
        layout.addStretch()
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
        self.profile_section.set_avatar_image(image_path)

    def _refresh_mood(self):
        self.profile_section.update_mood(mood.anger, mood.energy, mood.boredom, mood.affection)
        self._refresh_exp()

    def _refresh_exp(self):
        current_xp, xp_needed = exp_manager.progress()
        self.profile_section.update_exp(exp_manager.level, current_xp, xp_needed)

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
        self.content_stack.addWidget(SettingsPage())
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