import qtawesome as qta
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtWidgets import QPushButton

import ui.Theme as Theme


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
                    border-radius: 12px;
                    font-size: 18px;
                }}
                QPushButton:hover {{
                    color: white;
                }}
            """)