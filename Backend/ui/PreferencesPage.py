from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QScrollArea, QFrame, QCheckBox, QSlider
)

from Preferences import preferences, MONITOR_CATALOG, ACTION_CATALOG
from ui.Theme import PINK, PINK_SOFT, BG_BUBBLE


class IntervalSlider(QWidget):
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