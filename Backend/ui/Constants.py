import os

from PyQt6.QtGui import QFontDatabase

MOOD_REFRESH_INTERVAL_MS = 2000

TAB_HISTORY = 0
TAB_SETTINGS = 1
TAB_PREFERENCES = 2

ASSETS_DIR = os.path.join(os.path.dirname(__file__), "assets")
OXANIUM_FONT_PATH = os.path.join(ASSETS_DIR, "Oxanium-VariableFont_wght.ttf")

MOOD_IMAGE_MAP = {
    "ANGER": "venus_angry.png",
    "BORED": "venus_bored.png",
    "TIRED": "venus_tired.png",
    "POUTY": "venus_pouty.png",
    "NORMAL": "venus_profile.png",
}

_oxanium_family = None


def load_oxanium_family():
    """Loads (and caches) the Oxanium variable font family name."""
    global _oxanium_family
    if _oxanium_family is not None:
        return _oxanium_family

    font_id = QFontDatabase.addApplicationFont(OXANIUM_FONT_PATH)
    families = QFontDatabase.applicationFontFamilies(font_id) if font_id != -1 else []
    _oxanium_family = families[0] if families else "Segoe UI"
    return _oxanium_family