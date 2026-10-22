import os

import qtawesome as qta
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QPixmap, QPainter, QPainterPath, QColor, QPen
from PyQt6.QtWidgets import QFrame, QLabel, QVBoxLayout, QHBoxLayout, QProgressBar, QWidget

import ui.utils.Theme as Theme
from ui.utils.Typography import FONT_SIZE_XS, FONT_SIZE_LG, FONT_SIZE_XXL, FONT_SIZE_XXS, FONT_WEIGHT_BOLD
from ui.utils.Shapes import (
    RADIUS_SM,
    RADIUS_MD,
    RADIUS_LG,
    BORDER_THIN,
    BORDER_MEDIUM,
    ICON_SIZE_SM,
    ICON_SIZE_MD,
    AVATAR_SIZE_MD,
    PROGRESS_BAR_HEIGHT,
    PROGRESS_BAR_WIDTH,
    PROGRESS_BAR_LENGTH,
)
from ui.utils.Spacing import SPACE_XS, SPACE_SM, SPACE_MD


class _AvatarCircle(QLabel):
    """Round avatar widget supporting image files with fallback initials."""

    def __init__(self, image_path=None, initials="V"):
        super().__init__()
        self.setFixedSize(AVATAR_SIZE_MD, AVATAR_SIZE_MD)
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
                self.setPixmap(self._make_circular_pixmap(pixmap, AVATAR_SIZE_MD, border_width=BORDER_MEDIUM))
                self.setStyleSheet("background: transparent; border: none;")
                return

        # Fallback if image path is invalid or missing
        self.setText(self.initials)
        self.setStyleSheet(f"""
            background-color: {Theme.BG_ELEVATED};
            border: {BORDER_MEDIUM}px solid {Theme.ACCENT};
            border-radius: {AVATAR_SIZE_MD // 2}px;
            color: {Theme.ACCENT};
            font-size: {FONT_SIZE_XXL}px;
            font-weight: {FONT_WEIGHT_BOLD};
        """)

    def _make_circular_pixmap(self, src_pixmap, size, border_width=BORDER_MEDIUM):
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
        pen = QPen(QColor(Theme.ACCENT))
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
        # Fix 2: small horizontal margins so labels get the full card width.
        layout.setContentsMargins(SPACE_XS, SPACE_SM, SPACE_XS, SPACE_SM)
        layout.setSpacing(SPACE_XS)
        # Fix 3: no layout-wide alignment (it shrinks children to their size
        # hint). Individual widgets are aligned below instead.

        self.icon_label = QLabel()
        self.icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.icon_label.setStyleSheet("border: none; background: transparent;")

        self.name_label = QLabel(label)
        self.name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.bar = QProgressBar()
        self.bar.setOrientation(Qt.Orientation.Vertical)
        self.bar.setRange(0, 100)
        self.bar.setTextVisible(False)
        self.bar.setFixedSize(PROGRESS_BAR_WIDTH, PROGRESS_BAR_LENGTH)

        self.percent_label = QLabel("0%")
        self.percent_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Fix 3: icon and bar are centered individually; the text labels fill
        # the card width (their text is already centered).
        layout.addWidget(self.icon_label, alignment=Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(self.name_label)
        layout.addWidget(self.bar, alignment=Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(self.percent_label)

        self._apply_style()
        Theme.theme_signals.changed.connect(self._apply_style)

    def _apply_style(self):
        self.setStyleSheet(f"""
            QWidget {{
                background-color: #18051b;
                border-radius: {RADIUS_MD}px;
            }}
        """)
        self.icon_label.setPixmap(qta.icon(self.icon_name, color=Theme.ACCENT).pixmap(QSize(ICON_SIZE_MD, ICON_SIZE_MD)))
        self.name_label.setStyleSheet(
            f"color: {Theme.ACCENT_SOFT}; font-size: {FONT_SIZE_XXS}px; border: none; background: transparent;")
        self.bar.setStyleSheet(f"""
            QProgressBar {{
                background-color: {Theme.BG_ELEVATED};
                border: {BORDER_THIN}px solid {Theme.ACCENT};
                border-radius: {RADIUS_SM}px;
            }}
            QProgressBar::chunk {{
                background-color: {Theme.ACCENT};
                border-radius: {RADIUS_SM}px;
            }}
        """)
        self.percent_label.setStyleSheet(
            f"color: {Theme.ACCENT_SOFT}; font-size: {FONT_SIZE_XS}px; border: none; background: transparent;")

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
        layout.setContentsMargins(SPACE_MD, SPACE_MD, SPACE_MD, SPACE_MD)
        layout.setSpacing(SPACE_MD)

        profile_image_path = os.path.join(assets_dir, "venus_profile.png")

        header = QHBoxLayout()
        header.setSpacing(SPACE_MD)
        self.avatar = _AvatarCircle(image_path=profile_image_path, initials=initials)
        header.addWidget(self.avatar)

        name_column = QVBoxLayout()
        name_column.setSpacing(SPACE_XS)

        name_row = QHBoxLayout()
        name_row.setSpacing(SPACE_SM)
        name_label = QLabel(name)
        name_label.setStyleSheet(
            f"color: white; font-size: {FONT_SIZE_LG}px; font-weight: {FONT_WEIGHT_BOLD}; border: none; background: transparent;")
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
        self.xp_bar.setFixedHeight(PROGRESS_BAR_HEIGHT)
        layout.addWidget(self.xp_bar)

        stats_row = QHBoxLayout()
        # Fix 2: tighter gap between the stat cards.
        stats_row.setSpacing(SPACE_XS)

        self.anger_bar = _MoodStatBar("fa5s.angry", "Anger")
        self.energy_bar = _MoodStatBar("fa5s.bolt", "Energy")
        self.boredom_bar = _MoodStatBar("fa5s.tired", "Boredom")
        self.affection_bar = _MoodStatBar("fa5s.heart", "Affection")

        # Fix 4: equal stretch so every card gets the same share of the width.
        for stat_bar in (self.anger_bar, self.energy_bar, self.boredom_bar, self.affection_bar):
            stats_row.addWidget(stat_bar, 1)

        layout.addLayout(stats_row)

        self._apply_style()
        Theme.theme_signals.changed.connect(self._apply_style)

    def _apply_style(self):
        self.setStyleSheet(f"""
            QFrame {{
                background-color: {Theme.BG_ELEVATED};
                border: none;
                border-radius: {RADIUS_LG}px;
            }}
        """)
        self._name_heart.setPixmap(qta.icon("fa5s.heart", color=Theme.ACCENT).pixmap(QSize(ICON_SIZE_SM, ICON_SIZE_SM)))
        self.xp_bar.setStyleSheet(f"""
            QProgressBar {{
                background-color: #16051a;
                border: none;
                border-radius: {RADIUS_SM}px;
            }}
            QProgressBar::chunk {{
                background-color: {Theme.ACCENT};
                border-radius: {RADIUS_SM}px;
            }}
        """)
        self._xp_caption.setStyleSheet(
            f"color: {Theme.ACCENT_SOFT}; font-size: {FONT_SIZE_XS}px; border: none; background: transparent;")
        self.xp_value_label.setStyleSheet(
            f"color: {Theme.ACCENT_SOFT}; font-size: {FONT_SIZE_XS}px; border: none; background: transparent;")
        self.level_label.setStyleSheet(
            f"color: {Theme.ACCENT_SOFT}; font-size: {FONT_SIZE_XS}px; border: none; background: transparent;")

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