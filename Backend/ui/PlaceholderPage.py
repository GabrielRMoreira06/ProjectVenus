from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel

import ui.Theme as Theme


class PlaceholderPage(QWidget):
    def __init__(self, title):
        super().__init__()

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.label = QLabel(f"{title} — coming soon")
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.label)

        self._apply_style()
        Theme.theme_signals.changed.connect(self._apply_style)

    def _apply_style(self):
        self.label.setStyleSheet(
            f"color: {Theme.PINK_SOFT}; font-size: 20px; border: none; background: transparent;")