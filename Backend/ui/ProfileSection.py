import os

import qtawesome as qta
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QPixmap, QPainter, QPainterPath, QColor, QPen
from PyQt6.QtWidgets import QFrame, QLabel, QVBoxLayout, QHBoxLayout, QProgressBar, QWidget

import ui.Theme as Theme


class _AvatarCircle(QLabel):
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


class _MoodStatBar(QWidget):
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


class ProfileSection(QFrame):
    """Sidebar card: avatar, name, level/XP bar, and the four mood stat bars.

    Owns and applies its own theme styling in __init__, so it renders
    correctly the moment it's constructed — PanelWindow doesn't need to
    know about any of its internal widgets to style it.
    """

    def __init__(self, assets_dir, name="Venus", initials="V"):
        super().__init__()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 14, 12, 12)
        layout.setSpacing(10)

        profile_image_path = os.path.join(assets_dir, "venus_profile.png")

        header = QHBoxLayout()
        header.setSpacing(10)
        self.avatar = _AvatarCircle(image_path=profile_image_path, initials=initials)
        header.addWidget(self.avatar)

        name_column = QVBoxLayout()
        name_column.setSpacing(2)

        name_row = QHBoxLayout()
        name_row.setSpacing(6)
        name_label = QLabel(name)
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

        self.anger_bar = _MoodStatBar("fa5s.angry", "Anger")
        self.energy_bar = _MoodStatBar("fa5s.bolt", "Energy")
        self.boredom_bar = _MoodStatBar("fa5s.tired", "Boredom")
        self.affection_bar = _MoodStatBar("fa5s.heart", "Affection")

        for stat_bar in (self.anger_bar, self.energy_bar, self.boredom_bar, self.affection_bar):
            stats_row.addWidget(stat_bar)

        layout.addLayout(stats_row)

        self._apply_style()
        Theme.theme_signals.changed.connect(self._apply_style)

    def _apply_style(self):
        self.setStyleSheet(f"""
            QFrame {{
                background-color: {Theme.BG_BUBBLE};
                border: none;
                border-radius: 14px;
            }}
        """)
        self._name_heart.setPixmap(qta.icon("fa5s.heart", color=Theme.PINK).pixmap(QSize(13, 13)))
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

    def set_avatar_image(self, image_path):
        self.avatar.set_image(image_path)

    def update_mood(self, anger, energy, boredom, affection):
        self.anger_bar.set_value(anger)
        self.energy_bar.set_value(energy)
        self.boredom_bar.set_value(boredom)
        self.affection_bar.set_value(affection)

    def update_exp(self, level, current_xp, xp_needed):
        self.level_label.setText(f"Lv. {level}")
        self.xp_value_label.setText(f"{current_xp} / {xp_needed}")
        percent = int(100 * current_xp / xp_needed) if xp_needed else 0
        self.xp_bar.setValue(max(0, min(100, percent)))