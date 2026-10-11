import qtawesome as qta
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame, QStackedWidget
)

from ui.pages.PlaceholderPage import PlaceholderPage
from ui.pages.WallpaperPage import WallpaperPage
import ui.utils.Theme as Theme
from ui.utils.Typography import FONT_SIZE_MD
from ui.utils.Shapes import RADIUS_LG, RADIUS_XL, BORDER_THIN, ICON_SIZE_LG, NAV_TILE_HEIGHT, NAV_RAIL_WIDTH
from ui.utils.Spacing import SPACE_0, SPACE_SM, SPACE_MD

TOOL_ALARM = 0
TOOL_MEMORIES = 1
TOOL_WALLPAPER = 2


class ToolNavButton(QPushButton):
    def __init__(self, icon_name, label, active=False):
        super().__init__()
        self.icon_name = icon_name
        self._active = active
        self._hovered = False

        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(NAV_TILE_HEIGHT)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(SPACE_0, SPACE_0, SPACE_0, SPACE_0)
        layout.setSpacing(SPACE_SM)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._icon_label = QLabel()
        self._icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._icon_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

        self._text_label = QLabel(label)
        self._text_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._text_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

        layout.addWidget(self._icon_label)
        layout.addWidget(self._text_label)

        self._apply_style()
        Theme.theme_signals.changed.connect(self._apply_style)

    def set_active(self, active):
        self._active = active
        self._apply_style()

    def enterEvent(self, event):
        self._hovered = True
        self._apply_style()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hovered = False
        self._apply_style()
        super().leaveEvent(event)

    def _apply_style(self):
        highlighted = self._active or self._hovered
        color = "white" if highlighted else Theme.PINK_SOFT

        self._icon_label.setPixmap(qta.icon(self.icon_name, color=color).pixmap(QSize(ICON_SIZE_LG, ICON_SIZE_LG)))
        self._icon_label.setStyleSheet("border: none; background: transparent;")
        self._text_label.setStyleSheet(
            f"color: {color}; font-size: {FONT_SIZE_MD}px; border: none; background: transparent;")

        if self._active:
            self.setStyleSheet(f"""
                QPushButton {{
                    background-color: {Theme.BG_BUBBLE};
                    border: {BORDER_THIN}px solid {Theme.PINK};
                    border-radius: {RADIUS_LG}px;
                }}
            """)
        else:
            self.setStyleSheet(f"""
                QPushButton {{
                    background-color: transparent;
                    border: none;
                    border-radius: {RADIUS_LG}px;
                }}
            """)


class ToolsPage(QWidget):
    def __init__(self):
        super().__init__()

        root = QHBoxLayout(self)
        root.setContentsMargins(SPACE_0, SPACE_0, SPACE_0, SPACE_0)
        root.setSpacing(SPACE_MD)

        self.nav_buttons = [
            ToolNavButton("fa5s.bell", "Alarm", active=True),
            ToolNavButton("fa5s.images", "Memories"),
            ToolNavButton("fa5s.image", "Wallpaper"),
        ]

        self._nav_frame = QFrame()
        self._nav_frame.setObjectName("toolsNav")
        self._nav_frame.setFixedWidth(NAV_RAIL_WIDTH)

        nav_layout = QVBoxLayout(self._nav_frame)
        nav_layout.setContentsMargins(SPACE_0, SPACE_MD, SPACE_0, SPACE_MD)
        nav_layout.setSpacing(SPACE_SM)

        for index, button in enumerate(self.nav_buttons):
            button.clicked.connect(lambda _checked=False, i=index: self._switch_tool(i))
            nav_layout.addWidget(button)

        nav_layout.addStretch()
        root.addWidget(self._nav_frame)

        self.tool_stack = QStackedWidget()
        self.tool_stack.addWidget(PlaceholderPage("Alarm"))
        self.tool_stack.addWidget(PlaceholderPage("Memories"))
        self.tool_stack.addWidget(WallpaperPage())
        root.addWidget(self.tool_stack, stretch=1)

        self._apply_style()
        Theme.theme_signals.changed.connect(self._apply_style)

    def _switch_tool(self, index):
        self.tool_stack.setCurrentIndex(index)
        for button_index, button in enumerate(self.nav_buttons):
            button.set_active(button_index == index)

    def _apply_style(self):
        self._nav_frame.setStyleSheet(f"""
            #toolsNav {{
                background-color: {Theme.BG_PANEL};
                border: none;
                border-radius: {RADIUS_XL}px;
            }}
        """)