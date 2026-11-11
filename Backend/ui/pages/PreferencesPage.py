from PyQt6.QtCore import (
    Qt, pyqtSignal, pyqtProperty, QPropertyAnimation, QEasingCurve, QRectF
)
from PyQt6.QtGui import QPainter, QColor, QPen
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QScrollArea, QFrame, QSlider
)

from Preferences import preferences, MONITOR_CATALOG, ACTION_CATALOG, IDLE_COOLDOWN_SECONDS
import ui.utils.Theme as Theme

MAX_PACE = 72  # 72 cooldowns = 6h at the default 5 min cooldown


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

        track_color = QColor(Theme.ACCENT if self._checked else Theme.BG_ELEVATED)
        border_color = QColor(Theme.ACCENT if (self._checked or self._hovered) else Theme.ACCENT_SOFT)

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


class PaceSlider(QWidget):
    valueChangedPace = pyqtSignal(int)

    def __init__(self, initial_pace):
        super().__init__()

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(1, MAX_PACE)
        self.slider.setValue(max(1, min(MAX_PACE, initial_pace)))
        self.slider.valueChanged.connect(self._on_changed)

        self.value_label = QLabel(self._format(self.slider.value()))
        self.value_label.setFixedWidth(110)

        layout.addWidget(self.slider, stretch=1)
        layout.addWidget(self.value_label)

        self._apply_style()
        Theme.theme_signals.changed.connect(self._apply_style)

    def _apply_style(self):
        self.slider.setStyleSheet(f"""
            QSlider::groove:horizontal {{
                background: {Theme.BG_ELEVATED};
                height: 6px;
                border-radius: 3px;
            }}
            QSlider::handle:horizontal {{
                background: {Theme.ACCENT};
                width: 16px;
                margin: -6px 0;
                border-radius: 8px;
            }}
            QSlider::sub-page:horizontal {{
                background: {Theme.ACCENT};
                border-radius: 3px;
            }}
        """)
        self.value_label.setStyleSheet(
            f"color: {Theme.ACCENT_SOFT}; font-size: 12px; border: none; background: transparent;")

    def _on_changed(self, pace):
        self.value_label.setText(self._format(pace))
        self.valueChangedPace.emit(pace)

    @staticmethod
    def _format(pace):
        minutes = pace * IDLE_COOLDOWN_SECONDS // 60
        if minutes < 60:
            return f"{pace}  (~{minutes} min)"
        hours, remaining = divmod(minutes, 60)
        approx = f"{hours}h {remaining}m" if remaining else f"{hours}h"
        return f"{pace}  (~{approx})"


class InteractionRow(QFrame):
    def __init__(self, title, description, checked, on_toggled,
                 initial_pace=None, on_pace_changed=None):
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

        self.pace_slider = None

        if initial_pace is not None:
            pace_row = QHBoxLayout()

            self.pace_caption = QLabel("Pace (idle cooldowns):")
            pace_row.addWidget(self.pace_caption)

            self.pace_slider = PaceSlider(initial_pace)
            if on_pace_changed is not None:
                self.pace_slider.valueChangedPace.connect(on_pace_changed)
            pace_row.addWidget(self.pace_slider, stretch=1)

            layout.addLayout(pace_row)
        else:
            self.pace_caption = None

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
            f"color: {Theme.ACCENT_SOFT}; font-size: 12px; border: none; background: transparent;")
        if self.pace_caption is not None:
            self.pace_caption.setStyleSheet(
                f"color: {Theme.ACCENT_SOFT}; font-size: 12px; border: none; background: transparent;")


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

        for monitor_id, (label, description, default_pace) in MONITOR_CATALOG.items():
            initial_pace = None if default_pace is None else preferences.get_monitor_pace(monitor_id)

            row = InteractionRow(
                label, description,
                checked=preferences.is_monitor_enabled(monitor_id),
                on_toggled=lambda checked, m=monitor_id: preferences.set_monitor_enabled(m, checked),
                initial_pace=initial_pace,
                on_pace_changed=lambda pace, m=monitor_id: preferences.set_monitor_pace(m, pace),
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
        header_style = f"color: {Theme.ACCENT}; font-size: 16px; font-weight: bold; border: none; background: transparent;"
        self.monitors_header.setStyleSheet(header_style)
        self.actions_header.setStyleSheet(header_style)