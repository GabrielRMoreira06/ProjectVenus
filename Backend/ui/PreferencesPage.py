from PyQt6.QtCore import (
    Qt, pyqtSignal, pyqtProperty, QPropertyAnimation, QEasingCurve, QRectF
)
from PyQt6.QtGui import QPainter, QColor, QPen
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QScrollArea, QFrame, QSlider
)

from Preferences import preferences, MONITOR_CATALOG, ACTION_CATALOG
import ui.Theme as Theme


class ToggleSwitch(QWidget):
    """
    Small pill-shaped toggle switch with an animated sliding knob —
    replaces the default QCheckBox indicator, which can't be restyled
    into anything nicer than a plain square via QSS alone.

    Exposes the same shape of API a caller would expect from a
    checkbox: setChecked/isChecked and a `toggled(bool)` signal.
    """

    toggled = pyqtSignal(bool)

    def __init__(self, checked=False):
        super().__init__()
        self.setFixedSize(46, 26)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        self._checked = checked
        self._knob_pos = 1.0 if checked else 0.0
        self._hovered = False

        self._animation = QPropertyAnimation(self, b"knob_pos", self)
        self._animation.setDuration(160)
        self._animation.setEasingCurve(QEasingCurve.Type.OutCubic)

        Theme.theme_signals.changed.connect(self.update)

    # -- knob_pos as an animatable Qt property ------------------------

    def _get_knob_pos(self):
        return self._knob_pos

    def _set_knob_pos(self, value):
        self._knob_pos = value
        self.update()

    knob_pos = pyqtProperty(float, _get_knob_pos, _set_knob_pos)

    # -- public API -----------------------------------------------------

    def isChecked(self):
        return self._checked

    def setChecked(self, checked, animate=False):
        if self._checked == checked:
            return
        self._checked = checked

        if animate:
            self._animation.stop()
            self._animation.setStartValue(self._knob_pos)
            self._animation.setEndValue(1.0 if checked else 0.0)
            self._animation.start()
        else:
            self._knob_pos = 1.0 if checked else 0.0
            self.update()

    # -- interaction ------------------------------------------------------

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.setChecked(not self._checked, animate=True)
            self.toggled.emit(self._checked)
        super().mousePressEvent(event)

    def enterEvent(self, event):
        self._hovered = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hovered = False
        self.update()
        super().leaveEvent(event)

    # -- painting -----------------------------------------------------

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = QRectF(1, 1, self.width() - 2, self.height() - 2)
        radius = rect.height() / 2

        track_color = QColor(Theme.PINK if self._checked else Theme.BG_BUBBLE)
        border_color = QColor(Theme.PINK if (self._checked or self._hovered) else Theme.PINK_SOFT)

        painter.setPen(QPen(border_color, 1.5))
        painter.setBrush(track_color)
        painter.drawRoundedRect(rect, radius, radius)

        knob_diameter = rect.height() - 6
        travel = rect.width() - knob_diameter - 6
        knob_x = rect.left() + 3 + travel * self._knob_pos
        knob_y = rect.top() + (rect.height() - knob_diameter) / 2

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("white"))
        painter.drawEllipse(QRectF(knob_x, knob_y, knob_diameter, knob_diameter))

        painter.end()


class IntervalSlider(QWidget):
    valueChangedMinutes = pyqtSignal(int)

    def __init__(self, initial_minutes):
        super().__init__()

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(1, 360)
        self.slider.setValue(max(1, min(360, initial_minutes)))
        self.slider.valueChanged.connect(self._on_changed)

        self.value_label = QLabel(self._format(self.slider.value()))
        self.value_label.setFixedWidth(60)

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

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(6)

        header = QHBoxLayout()

        self.title_label = QLabel(title)

        self.toggle = ToggleSwitch(checked=checked)
        self.toggle.toggled.connect(on_toggled)

        header.addWidget(self.title_label)
        header.addStretch()
        header.addWidget(self.toggle)
        layout.addLayout(header)

        self.description_label = QLabel(description)
        self.description_label.setWordWrap(True)
        layout.addWidget(self.description_label)

        self.interval_slider = None

        if initial_minutes is not None:
            interval_row = QHBoxLayout()

            self.interval_caption = QLabel("Check every:")
            interval_row.addWidget(self.interval_caption)

            self.interval_slider = IntervalSlider(initial_minutes)
            if on_interval_changed is not None:
                self.interval_slider.valueChangedMinutes.connect(on_interval_changed)
            interval_row.addWidget(self.interval_slider, stretch=1)

            layout.addLayout(interval_row)
        else:
            self.interval_caption = None

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
        if self.interval_caption is not None:
            self.interval_caption.setStyleSheet(
                f"color: {Theme.PINK_SOFT}; font-size: 12px; border: none; background: transparent;")


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

        self.monitors_header = QLabel("Passive behaviors")
        content_layout.addWidget(self.monitors_header)

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

        self.actions_header = QLabel("Actions")
        content_layout.addWidget(self.actions_header)

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

        self._apply_style()
        Theme.theme_signals.changed.connect(self._apply_style)

    def _apply_style(self):
        header_style = f"color: {Theme.PINK}; font-size: 16px; font-weight: bold; border: none; background: transparent;"
        self.monitors_header.setStyleSheet(header_style)
        self.actions_header.setStyleSheet(header_style)