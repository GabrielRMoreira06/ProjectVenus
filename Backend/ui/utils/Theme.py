from PyQt6.QtCore import QObject, pyqtSignal


class _ThemeSignals(QObject):
    changed = pyqtSignal()


theme_signals = _ThemeSignals()

THEMES = {
    "classic_pink": {
        "ACCENT": "#ff2fb0",
        "ACCENT_SOFT": "#ff7fce",
        "FOCUS": "#ff00a0",
        "BG_DARK": "#0a0007",
        "BG_SURFACE": "#170a14",
        "BG_ELEVATED": "#1f0f1c",
    },
    "violet_dusk": {
        "ACCENT": "#b24fff",
        "ACCENT_SOFT": "#d59bff",
        "FOCUS": "#9d00ff",
        "BG_DARK": "#07000a",
        "BG_SURFACE": "#120a17",
        "BG_ELEVATED": "#1a0f1f",
    },
    "crimson_night": {
        "ACCENT": "#ff3860",
        "ACCENT_SOFT": "#ff8fa3",
        "FOCUS": "#ff0033",
        "BG_DARK": "#0a0002",
        "BG_SURFACE": "#170608",
        "BG_ELEVATED": "#1f0a0d",
    },
}
# Maps Gemini's UPDATE_UI_THEME enum values to THEMES keys.
THEME_ALIASES = {
    "CLASSIC": "classic_pink",
    "VIOLET": "violet_dusk",
    "CRIMSON": "crimson_night",
}

_current_scheme_name = "classic_pink"


def _apply_scheme(name):
    global ACCENT, FOCUS, ACCENT_SOFT, BG_DARK, BG_SURFACE, BG_ELEVATED, _current_scheme_name
    scheme = THEMES[name]
    ACCENT = scheme["ACCENT"]
    FOCUS = scheme["FOCUS"]
    ACCENT_SOFT = scheme["ACCENT_SOFT"]
    BG_DARK = scheme["BG_DARK"]
    BG_SURFACE = scheme["BG_SURFACE"]
    BG_ELEVATED = scheme["BG_ELEVATED"]
    _current_scheme_name = name


_apply_scheme(_current_scheme_name)  # sets initial ACCENT, ACCENT_SOFT, etc.


def set_theme(name):
    """Switch the active color scheme. name: 'classic_pink' | 'violet_dusk' | 'crimson_night'."""
    if name not in THEMES:
        raise ValueError(f"Unknown theme '{name}'. Options: {list(THEMES)}")
    _apply_scheme(name)
    theme_signals.changed.emit()


def current_theme_name():
    return _current_scheme_name