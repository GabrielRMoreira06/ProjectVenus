"""
PanelWindow.py

Skeleton for Venus's side panel UI (message history, settings,
preferences). The History tab is live (see ai.ChatHistory), including
image thumbnails for user-sent images. The input bar is a
MessageComposer(compact=True) — see MessageComposer.py for why the
composer itself is shared with TextInput.InputWindow rather than each
window having its own paste/send logic.

History / Settings / Preferences are now real tabs: clicking a
NavButton swaps content_stack's page and updates which button looks
active. Settings and Preferences are still empty placeholder pages —
there's nothing to configure yet, so they just say so rather than
faking controls that don't do anything.

Sidebar profile section: Anger/Energy/Boredom/Affection are real
(polled from MoodController). Avatar/name/Level/XP are placeholders —
there is no leveling system in the backend to source real numbers
from.

A close button (top-right of the main area) just hides the window,
same end state as pressing the hotkey while it's open.

Fonts/icons: headline/UI font is Oxanium (ui/assets/Oxanium-VariableFont_wght.ttf),
loaded once via QFontDatabase. All former emoji glyphs (nav icons, mood
icons, close button, footer heart) now render through qtawesome instead.

Dragging: the window is frameless, so there's no OS title bar to grab.
The sidebar and main-area backgrounds are DraggableFrame instances —
clicking anywhere on their empty background (not on a button, bubble,
etc.) and moving the mouse drags the whole panel.
"""

import os
import sys

import keyboard
import qtawesome as qta
from PyQt6.QtCore import Qt, QTimer, QSize, pyqtSignal
from PyQt6.QtGui import QFontDatabase
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QScrollArea, QFrame, QProgressBar, QStackedWidget,
    QCheckBox, QSlider,
)

from Preferences import preferences, MONITOR_CATALOG, ACTION_CATALOG

from ai.ChatHistory import chat_history
from ai.MoodController import mood
from ui.ImageUtils import pil_to_qpixmap
from ui.MessageComposer import MessageComposer
from ui.Theme import PINK, PINK_SOFT, BG_DARK, BG_PANEL, BG_BUBBLE

MOOD_REFRESH_INTERVAL_MS = 2000
THUMBNAIL_MAX_SIZE = (200, 150)

# Index of each page inside content_stack — kept as names rather than
# bare 0/1/2 so _switch_tab() calls read as what they mean.
TAB_HISTORY = 0
TAB_SETTINGS = 1
TAB_PREFERENCES = 2

ASSETS_DIR = os.path.join(os.path.dirname(__file__), "assets")
OXANIUM_FONT_PATH = os.path.join(ASSETS_DIR, "Oxanium-VariableFont_wght.ttf")

# Cached after first load so repeated PanelWindow instances (or the
# standalone preview entry point) don't re-register the font family
# with Qt every time.
_oxanium_family = None


def _load_oxanium_family():
    """Register the Oxanium variable font with Qt and return its family name.

    Falls back to "Segoe UI" if the font file is missing/unreadable so a
    bad asset path doesn't crash the whole panel.
    """
    global _oxanium_family
    if _oxanium_family is not None:
        return _oxanium_family

    font_id = QFontDatabase.addApplicationFont(OXANIUM_FONT_PATH)
    families = QFontDatabase.applicationFontFamilies(font_id) if font_id != -1 else []
    _oxanium_family = families[0] if families else "Segoe UI"
    return _oxanium_family


class DraggableFrame(QFrame):
    """
    A QFrame that lets the user drag the frameless top-level window by
    clicking its background and moving the mouse. Mouse events on child
    widgets (buttons, labels, the scroll area, etc.) aren't affected —
    this only fires when the click lands on empty frame background.
    """

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
    """
    Sidebar entry (History / Settings / Preferences). set_active()
    can be called again after construction — PanelWindow uses this to
    restyle every button whenever the selected tab changes.
    """

    def __init__(self, icon_name, label, active=False):
        super().__init__(f"  {label}                                   >")
        self.icon_name = icon_name
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(64)
        self.set_active(active)

    def set_active(self, active):
        self._active = active

        icon_color = "white" if active else PINK_SOFT
        self.setIcon(qta.icon(self.icon_name, color=icon_color))
        self.setIconSize(QSize(20, 20))

        self._apply_style()

    def _apply_style(self):
        if self._active:
            self.setStyleSheet(f"""
                QPushButton {{
                    text-align: left;
                    padding-left: 18px;
                    background-color: {BG_BUBBLE};
                    color: white;
                    border: 1px solid {PINK};
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
                    color: {PINK_SOFT};
                    border: none;
                    font-size: 18px;
                }}
                QPushButton:hover {{
                    color: white;
                }}
            """)


class AvatarCircle(QLabel):
    """Placeholder round avatar — swap for a real portrait asset later."""

    def __init__(self, initials="V"):
        super().__init__(initials)
        self.setFixedSize(78, 78)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setStyleSheet(f"""
            background-color: {BG_BUBBLE};
            border: 2px solid {PINK};
            border-radius: 39px;
            color: {PINK};
            font-size: 24px;
            font-weight: bold;
        """)


class MoodStatBar(QWidget):
    """
    One vertical mood stat: qtawesome icon, label, a vertical bar, and a
    percent readout below it. set_value() is the only thing that changes
    at runtime — everything else is built once.
    """

    def __init__(self, icon_name, label):
        super().__init__()

        self.setStyleSheet(f"""
            QWidget {{
                background-color: #18051b;
                border-radius: 10px;
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 8, 6, 8)
        layout.setSpacing(4)
        layout.setAlignment(Qt.AlignmentFlag.AlignHCenter)

        icon_label = QLabel()
        icon_label.setPixmap(qta.icon(icon_name, color=PINK).pixmap(QSize(18, 18)))
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_label.setStyleSheet("border: none; background: transparent;")

        name_label = QLabel(label)
        name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        name_label.setStyleSheet(f"color: {PINK_SOFT}; font-size: 8px; border: none; background: transparent;")

        self.bar = QProgressBar()
        self.bar.setOrientation(Qt.Orientation.Vertical)
        self.bar.setRange(0, 100)
        self.bar.setTextVisible(False)
        self.bar.setFixedSize(18, 92)
        self.bar.setStyleSheet(f"""
            QProgressBar {{
                background-color: {BG_BUBBLE};
                border: 1px solid {PINK};
                border-radius: 7px;
            }}
            QProgressBar::chunk {{
                background-color: {PINK};
                border-radius: 5px;
            }}
        """)

        self.percent_label = QLabel("0%")
        self.percent_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.percent_label.setStyleSheet(f"color: {PINK_SOFT}; font-size: 11px; border: none; background: transparent;")

        layout.addWidget(icon_label)
        layout.addWidget(name_label)
        layout.addWidget(self.bar, alignment=Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(self.percent_label)

    def set_value(self, value):
        value = max(0, min(100, int(value)))
        self.bar.setValue(value)
        self.percent_label.setText(f"{value}%")


class ChatBubble(QFrame):
    def __init__(self, text, timestamp, side="left", image=None):
        super().__init__()

        column = QVBoxLayout()
        column.setSpacing(8)

        if image is not None:
            thumbnail_label = QLabel()
            pixmap = pil_to_qpixmap(image).scaled(
                THUMBNAIL_MAX_SIZE[0], THUMBNAIL_MAX_SIZE[1],
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            thumbnail_label.setPixmap(pixmap)

            column.addWidget(
                thumbnail_label,
                alignment=Qt.AlignmentFlag.AlignRight if side == "right" else Qt.AlignmentFlag.AlignLeft,
            )

        if text:
            bubble = QLabel(text)
            bubble.setWordWrap(True)
            bubble.setStyleSheet(f"""
                QLabel {{
                    background-color: {BG_BUBBLE};
                    color: white;
                    padding: 14px 18px;
                    border-radius: 12px;
                    font-size: 18px;
                }}
            """)
            column.addWidget(bubble)

        time_label = QLabel(timestamp)
        time_label.setStyleSheet(f"color: {PINK_SOFT}; font-size: 11px;")
        column.addWidget(
            time_label,
            alignment=Qt.AlignmentFlag.AlignRight if side == "right" else Qt.AlignmentFlag.AlignLeft,
        )

        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)

        if side == "left":
            row.addLayout(column)
            row.addStretch()
        else:
            row.addStretch()
            row.addLayout(column)



class PlaceholderPage(QWidget):
    """Empty stand-in for Settings/Preferences — nothing to configure yet."""

    def __init__(self, title):
        super().__init__()

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        label = QLabel(f"{title} — coming soon")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setStyleSheet(f"color: {PINK_SOFT}; font-size: 20px; border: none; background: transparent;")
        layout.addWidget(label)

class IntervalSlider(QWidget):
    """
    Horizontal slider in whole minutes (1–1440, i.e. up to 24h), with a
    live label showing the formatted duration. Its own widget so
    InteractionRow doesn't duplicate the value<->label glue per row.
    """

    valueChangedMinutes = pyqtSignal(int)

    def __init__(self, initial_minutes):
        super().__init__()

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(1, 1440)
        self.slider.setValue(max(1, min(1440, initial_minutes)))
        self.slider.setStyleSheet(f"""
            QSlider::groove:horizontal {{
                background: {BG_BUBBLE};
                height: 6px;
                border-radius: 3px;
            }}
            QSlider::handle:horizontal {{
                background: {PINK};
                width: 16px;
                margin: -6px 0;
                border-radius: 8px;
            }}
            QSlider::sub-page:horizontal {{
                background: {PINK};
                border-radius: 3px;
            }}
        """)
        self.slider.valueChanged.connect(self._on_changed)

        self.value_label = QLabel(self._format(self.slider.value()))
        self.value_label.setFixedWidth(60)
        self.value_label.setStyleSheet(f"color: {PINK_SOFT}; font-size: 12px; border: none; background: transparent;")

        layout.addWidget(self.slider, stretch=1)
        layout.addWidget(self.value_label)

    def _on_changed(self, minutes):
        self.value_label.setText(self._format(minutes))
        self.valueChangedMinutes.emit(minutes)

    @staticmethod
    def _format(minutes):
        if minutes < 60:
            return f"{minutes} min"
        hours, remaining = divmod(minutes, 60)
        return f"{hours}h {remaining}m" if remaining else f"{hours}h"


class InteractionRow(QFrame):
    """
    One toggleable "interaction" in the Preferences tab.

    Passive monitors pass initial_minutes/on_interval_changed and get
    a checkbox + interval slider + description. Gemini ACTIONS omit
    those two arguments and get a checkbox + description only —
    there's no polling interval to set, since Gemini decides per-turn
    whether to use one; disabling an action just pulls it out of
    Prompts.py's ACTION list/explanation (see Preferences.py).
    """

    def __init__(self, title, description, checked, on_toggled,
                 initial_minutes=None, on_interval_changed=None):
        super().__init__()

        self.setStyleSheet("""
            QFrame {
                background-color: #18051b;
                border-radius: 12px;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(6)

        header = QHBoxLayout()

        self.checkbox = QCheckBox(title)
        self.checkbox.setChecked(checked)
        self.checkbox.setStyleSheet("""
            QCheckBox {
                color: white;
                font-size: 15px;
                font-weight: bold;
                border: none;
                background: transparent;
            }
            QCheckBox::indicator {
                width: 18px;
                height: 18px;
            }
        """)
        self.checkbox.toggled.connect(on_toggled)

        header.addWidget(self.checkbox)
        header.addStretch()
        layout.addLayout(header)

        description_label = QLabel(description)
        description_label.setWordWrap(True)
        description_label.setStyleSheet(f"color: {PINK_SOFT}; font-size: 12px; border: none; background: transparent;")
        layout.addWidget(description_label)

        self.interval_slider = None

        if initial_minutes is not None:
            interval_row = QHBoxLayout()

            interval_caption = QLabel("Check every:")
            interval_caption.setStyleSheet(f"color: {PINK_SOFT}; font-size: 12px; border: none; background: transparent;")
            interval_row.addWidget(interval_caption)

            self.interval_slider = IntervalSlider(initial_minutes)
            if on_interval_changed is not None:
                self.interval_slider.valueChangedMinutes.connect(on_interval_changed)
            interval_row.addWidget(self.interval_slider, stretch=1)

            layout.addLayout(interval_row)


class PreferencesPage(QWidget):
    """
    Real Preferences tab, backed by Preferences.py (preferences.json).
    Monitors get a checkbox + interval slider; actions get a checkbox
    only (see InteractionRow). Every change is applied immediately —
    monitors live (BaseMonitor reads enabled/interval fresh every
    loop), actions on the next prompt GeminiWorker builds.
    """

    def __init__(self):
        super().__init__()

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setSpacing(12)

        monitors_header = QLabel("Passive behaviors")
        monitors_header.setStyleSheet(f"color: {PINK}; font-size: 16px; font-weight: bold; border: none; background: transparent;")
        content_layout.addWidget(monitors_header)

        for monitor_id, (label, description, _default) in MONITOR_CATALOG.items():
            initial_minutes = max(1, preferences.get_monitor_interval(monitor_id) // 60)

            row = InteractionRow(
                label, description,
                checked=preferences.is_monitor_enabled(monitor_id),
                on_toggled=lambda checked, m=monitor_id: preferences.set_monitor_enabled(m, checked),
                initial_minutes=initial_minutes,
                on_interval_changed=lambda minutes, m=monitor_id: preferences.set_monitor_interval(m, minutes * 60),
            )
            content_layout.addWidget(row)

        actions_header = QLabel("Actions")
        actions_header.setStyleSheet(f"color: {PINK}; font-size: 16px; font-weight: bold; border: none; background: transparent;")
        content_layout.addWidget(actions_header)

        for action_id, (label, description) in ACTION_CATALOG.items():
            row = InteractionRow(
                label, description,
                checked=preferences.is_action_enabled(action_id),
                on_toggled=lambda checked, a=action_id: preferences.set_action_enabled(a, checked),
            )
            content_layout.addWidget(row)

        content_layout.addStretch()
        scroll.setWidget(content)
        outer.addWidget(scroll)

class PanelWindow(QWidget):

    toggle_requested = pyqtSignal()
    message_added = pyqtSignal(dict)

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
        self.message_added.connect(self._append_message)

        self.setStyleSheet(f"""
            QWidget {{
                background-color: {BG_DARK};
                color: white;
                font-family: "{self.font_family}";
            }}
            QScrollBar:vertical {{
                background: #16051a;
                width: 12px;
                margin: 4px;
            }}
            QScrollBar::handle:vertical {{
                background: {PINK};
                border-radius: 6px;
                min-height: 28px;
            }}
            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical {{
                height: 0px;
            }}
        """)

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(14)

        root.addWidget(self._build_sidebar())
        root.addWidget(self._build_main_area(), stretch=1)

        # Backfills anything already said before the panel was ever
        # opened (e.g. the boot greeting), then subscribes for
        # everything from here on.
        for message in chat_history.get_all():
            self._append_message(message)

        chat_history.subscribe(lambda message: self.message_added.emit(message))

        # Mood has no "changed" event to subscribe to (see
        # MoodController) — polled instead, same spirit as Unity
        # polling /response.
        self._mood_timer = QTimer(self)
        self._mood_timer.timeout.connect(self._refresh_mood)
        self._mood_timer.start(MOOD_REFRESH_INTERVAL_MS)
        self._refresh_mood()

    # ------------------------------------------------------------------
    # Sidebar
    # ------------------------------------------------------------------

    def _build_sidebar(self):
        sidebar = DraggableFrame()
        sidebar.setFixedWidth(240)
        sidebar.setStyleSheet(f"""
            QFrame {{
                background-color: {BG_PANEL};
                border: none;
                border-radius: 18px;
            }}
        """)

        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(16, 20, 16, 16)
        layout.setSpacing(14)

        history_button = NavButton("fa5s.comment", "History", active=True)
        settings_button = NavButton("fa5s.cog", "Settings")
        preferences_button = NavButton("fa5s.sliders-h", "Preferences")

        history_button.clicked.connect(lambda: self._switch_tab(TAB_HISTORY))
        settings_button.clicked.connect(lambda: self._switch_tab(TAB_SETTINGS))
        preferences_button.clicked.connect(lambda: self._switch_tab(TAB_PREFERENCES))

        self.nav_buttons = [history_button, settings_button, preferences_button]

        layout.addWidget(history_button)
        layout.addWidget(settings_button)
        layout.addWidget(preferences_button)

        divider = QFrame()
        divider.setFixedHeight(1)
        divider.setStyleSheet(f"background-color: {PINK}; border: none;")
        layout.addSpacing(4)
        layout.addWidget(divider)

        layout.addWidget(self._build_profile_section())
        layout.addStretch()

        heart = QLabel()
        heart.setPixmap(qta.icon("fa5s.heart", color=PINK).pixmap(QSize(22, 22)))
        heart.setStyleSheet("border: none; background: transparent;")
        layout.addWidget(heart, alignment=Qt.AlignmentFlag.AlignLeft)

        return sidebar

    def _switch_tab(self, index):
        self.content_stack.setCurrentIndex(index)
        for button_index, button in enumerate(self.nav_buttons):
            button.set_active(button_index == index)

    def _build_profile_section(self):
        container = QFrame()
        container.setStyleSheet(f"""
            QFrame {{
                background-color: {BG_BUBBLE};
                border: none;
                border-radius: 14px;
            }}
        """)
        layout = QVBoxLayout(container)
        # Increased padding (top, left, bottom, right)
        layout.setContentsMargins(12, 14, 12, 12)
        layout.setSpacing(10)

        header = QHBoxLayout()
        header.setSpacing(10)
        header.addWidget(AvatarCircle("V"))

        name_column = QVBoxLayout()
        name_column.setSpacing(2)

        name_row = QHBoxLayout()
        name_row.setSpacing(6)
        name_label = QLabel("Venus")
        name_label.setStyleSheet("color: white; font-size: 16px; font-weight: bold; border: none; background: transparent;")
        name_heart = QLabel()
        name_heart.setPixmap(qta.icon("fa5s.heart", color=PINK).pixmap(QSize(13, 13)))
        name_heart.setStyleSheet("border: none; background: transparent;")
        name_row.addWidget(name_label)
        name_row.addWidget(name_heart)
        name_row.addStretch()

        level_label = QLabel("Lv. —")
        level_label.setStyleSheet(f"color: {PINK_SOFT}; font-size: 11px; border: none; background: transparent;")

        name_column.addLayout(name_row)
        name_column.addWidget(level_label)

        header.addLayout(name_column)
        header.addStretch()
        layout.addLayout(header)

        xp_row = QHBoxLayout()
        xp_caption = QLabel("XP")
        xp_caption.setStyleSheet(f"color: {PINK_SOFT}; font-size: 11px; border: none; background: transparent;")
        xp_value = QLabel("— / —")
        xp_value.setStyleSheet(f"color: {PINK_SOFT}; font-size: 11px; border: none; background: transparent;")
        xp_row.addWidget(xp_caption)
        xp_row.addStretch()
        xp_row.addWidget(xp_value)
        layout.addLayout(xp_row)

        xp_bar = QProgressBar()
        xp_bar.setRange(0, 100)
        xp_bar.setValue(0)
        xp_bar.setTextVisible(False)
        xp_bar.setFixedHeight(10)
        xp_bar.setStyleSheet(f"""
            QProgressBar {{
                background-color: #16051a;
                border: none;
                border-radius: 5px;
            }}
            QProgressBar::chunk {{
                background-color: {PINK};
                border-radius: 2px;
            }}
        """)
        layout.addWidget(xp_bar)

        stats_row = QHBoxLayout()
        stats_row.setSpacing(6)

        self.anger_bar = MoodStatBar("fa5s.angry", "Anger")
        self.energy_bar = MoodStatBar("fa5s.bolt", "Energy")
        self.boredom_bar = MoodStatBar("fa5s.tired", "Boredom")
        self.affection_bar = MoodStatBar("fa5s.heart", "Affection")

        for stat_bar in (self.anger_bar, self.energy_bar, self.boredom_bar, self.affection_bar):
            stats_row.addWidget(stat_bar)

        layout.addLayout(stats_row)

        return container

    def _refresh_mood(self):
        self.anger_bar.set_value(mood.anger)
        self.energy_bar.set_value(mood.energy)
        self.boredom_bar.set_value(mood.boredom)
        self.affection_bar.set_value(mood.affection)

    # ------------------------------------------------------------------
    # Main area (header + tab content)
    # ------------------------------------------------------------------

    def _build_main_area(self):
        container = DraggableFrame()
        container.setObjectName("mainArea")

        container.setStyleSheet(f"""
            #mainArea {{
                background-color: #080108;
            }}
        """)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(20, 16, 20, 20)
        layout.setSpacing(14)

        layout.addLayout(self._build_header())

        self.content_stack = QStackedWidget()
        self.content_stack.addWidget(self._build_history_page())
        self.content_stack.addWidget(PlaceholderPage("Settings"))
        self.content_stack.addWidget(PreferencesPage())
        layout.addWidget(self.content_stack, stretch=1)

        return container

    def _build_history_page(self):
        """Everything the History tab shows — chat area + composer bar."""
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)

        layout.addWidget(self._build_chat_area(), stretch=1)
        layout.addWidget(self._build_input_bar())

        return page

    def _build_header(self):
        """Just the close button for now — hides the panel, same as toggling it off."""
        header = QHBoxLayout()
        header.addStretch()

        close_button = QPushButton()
        close_button.setIcon(qta.icon("fa5s.times", color=PINK_SOFT, color_active="white"))
        close_button.setIconSize(QSize(16, 16))
        close_button.setFixedSize(32, 32)
        close_button.setCursor(Qt.CursorShape.PointingHandCursor)
        close_button.clicked.connect(self.hide)
        close_button.setStyleSheet(f"""
            QPushButton {{
                background-color: #16051a;
                border: 1px solid {PINK};
                border-radius: 10px;
                color: {PINK_SOFT};
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {PINK};
                color: white;
            }}
        """)
        header.addWidget(close_button)

        return header

    def _build_chat_area(self):
        self.chat_scroll = QScrollArea()
        self.chat_scroll.setWidgetResizable(True)
        self.chat_scroll.setStyleSheet(f"""
            QScrollArea {{
                background-color: #080108;
                border: none;
            }}
            QScrollArea > QWidget > QWidget {{
                background-color: #080108;
            }}
        """)

        content = QWidget()
        self.messages_layout = QVBoxLayout(content)
        self.messages_layout.setSpacing(14)
        self.messages_layout.setContentsMargins(12, 12, 12, 12)
        self.messages_layout.addStretch()  # keeps bubbles pinned to the top as they accumulate

        self.chat_scroll.setWidget(content)
        return self.chat_scroll

    def _append_message(self, message):
        side = "right" if message["role"] == "user" else "left"
        bubble = ChatBubble(
            message["text"], message["timestamp"],
            side=side, image=message.get("image"),
        )

        # Inserted before the trailing stretch, so new bubbles land at
        # the bottom instead of pushing the stretch down with them.
        insert_index = self.messages_layout.count() - 1
        self.messages_layout.insertWidget(insert_index, bubble)

        QTimer.singleShot(0, self._scroll_to_bottom)

    def _scroll_to_bottom(self):
        scrollbar = self.chat_scroll.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def _build_input_bar(self):
        bar = QFrame()
        bar.setStyleSheet(f"""
            QFrame {{
                background-color: #16051a;
                border: 2px solid {PINK};
                border-radius: 16px;
            }}
        """)
        bar.setMinimumHeight(64)  # not fixed — grows to fit the image preview row when present

        layout = QHBoxLayout(bar)
        layout.setContentsMargins(14, 10, 14, 10)

        self.composer = MessageComposer(
            self.process_question, compact=True, placeholder="Type a message..."
        )
        layout.addWidget(self.composer)

        return bar



    # ------------------------------------------------------------------
    # Show/hide
    # ------------------------------------------------------------------

    def toggle(self):
        if self.isVisible():
            self.hide()
        else:
            self.show()
            self.raise_()
            self.activateWindow()


def start_panel_window(process_question, hotkey="ctrl+alt+h"):
    """
    Standalone entry point — only useful for previewing the panel by
    itself. The real app constructs PanelWindow inside
    TextInput.start_input_window() instead, since only one
    QApplication can exist per process.
    """
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    window = PanelWindow(process_question)
    keyboard.add_hotkey(hotkey, window.toggle_requested.emit)
    print(f"[PanelWindow] Hotkey '{hotkey}' registered globally.")

    sys.exit(app.exec())