"""
SettingsPage.py

Standalone app settings — voice output tuning and OS integration.
Separate from PreferencesPage, which toggles passive monitors/actions.
"""

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea, QFrame, QSlider
)

from Preferences import preferences
from ai import StartupManager
from ui.PreferencesPage import ToggleSwitch
import ui.Theme as Theme


class SettingRow(QFrame):
    def __init__(self, title, description, control):
        super().__init__()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(6)

        header = QHBoxLayout()
        self.title_label = QLabel(title)
        header.addWidget(self.title_label)
        header.addStretch()
        header.addWidget(control)
        layout.addLayout(header)

        self.description_label = QLabel(description)
        self.description_label.setWordWrap(True)
        layout.addWidget(self.description_label)

        self._apply_style()
        Theme.theme_signals.changed.connect(self._apply_style)

    def _apply_style(self):
        self.setStyleSheet("""
            QFrame {
                background-color: #18051b;
                border-radius: 12px;
            }
        """)
        self.title_label.setStyleSheet(
            "color: white; font-size: 15px; font-weight: bold; border: none; background: transparent;")
        self.description_label.setStyleSheet(
            f"color: {Theme.PINK_SOFT}; font-size: 12px; border: none; background: transparent;")


class VolumeSlider(QWidget):
    valueChangedPercent = pyqtSignal(int)

    def __init__(self, initial_percent):
        super().__init__()
        self.setFixedWidth(180)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(0, 100)
        self.slider.setValue(max(0, min(100, initial_percent)))
        self.slider.valueChanged.connect(self._on_changed)

        self.value_label = QLabel(f"{self.slider.value()}%")
        self.value_label.setFixedWidth(40)

        layout.addWidget(self.slider, stretch=1)
        layout.addWidget(self.value_label)

        self._apply_style()
        Theme.theme_signals.changed.connect(self._apply_style)

    def _apply_style(self):
        self.slider.setStyleSheet(f"""
            QSlider::groove:horizontal {{
                background: {Theme.BG_BUBBLE};
                height: 6px;
                border-radius: 3px;
            }}
            QSlider::handle:horizontal {{
                background: {Theme.PINK};
                width: 16px;
                margin: -6px 0;
                border-radius: 8px;
            }}
            QSlider::sub-page:horizontal {{
                background: {Theme.PINK};
                border-radius: 3px;
            }}
        """)
        self.value_label.setStyleSheet(
            f"color: {Theme.PINK_SOFT}; font-size: 12px; border: none; background: transparent;")

    def _on_changed(self, value):
        self.value_label.setText(f"{value}%")
        self.valueChangedPercent.emit(value)


class SettingsPage(QWidget):
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

        self.voice_header = QLabel("Voice")
        content_layout.addWidget(self.voice_header)

        volume_slider = VolumeSlider(preferences.get_voice_volume())
        volume_slider.valueChangedPercent.connect(preferences.set_voice_volume)
        content_layout.addWidget(SettingRow(
            "Voice volume",
            "Overall loudness of Venus's spoken responses.",
            volume_slider,
        ))

        robotic_toggle = ToggleSwitch(checked=preferences.is_robotic_effect_enabled())
        robotic_toggle.toggled.connect(preferences.set_robotic_effect_enabled)
        content_layout.addWidget(SettingRow(
            "Robotic voice effect",
            "Applies a synthetic modulation on top of the TTS voice.",
            robotic_toggle,
        ))

        self.startup_header = QLabel("Startup")
        content_layout.addWidget(self.startup_header)

        startup_toggle = ToggleSwitch(checked=StartupManager.is_enabled())
        startup_toggle.toggled.connect(StartupManager.set_enabled)
        content_layout.addWidget(SettingRow(
            "Start with Windows",
            "Launches Venus automatically when you log in.",
            startup_toggle,
        ))

        content_layout.addStretch()
        scroll.setWidget(content)
        outer.addWidget(scroll)

        self._apply_style()
        Theme.theme_signals.changed.connect(self._apply_style)

    def _apply_style(self):
        header_style = f"color: {Theme.PINK}; font-size: 16px; font-weight: bold; border: none; background: transparent;"
        self.voice_header.setStyleSheet(header_style)
        self.startup_header.setStyleSheet(header_style)