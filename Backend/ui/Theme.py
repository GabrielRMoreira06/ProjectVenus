from PyQt6.QtCore import QObject, pyqtSignal


class _ThemeSignals(QObject):
    changed = pyqtSignal()


theme_signals = _ThemeSignals()

THEMES = {
    "classic_pink": {
        "PINK": "#ff2fb0",
        "PINK_SOFT": "#ff7fce",
        "BG_DARK": "#0a0007",
        "BG_PANEL": "#170a14",
        "BG_BUBBLE": "#1f0f1c",
    },
    "violet_dusk": {
        "PINK": "#b24fff",
        "PINK_SOFT": "#d59bff",
        "BG_DARK": "#07000a",
        "BG_PANEL": "#120a17",
        "BG_BUBBLE": "#1a0f1f",
    },
    "crimson_night": {
        "PINK": "#ff3860",
        "PINK_SOFT": "#ff8fa3",
        "BG_DARK": "#0a0002",
        "BG_PANEL": "#170608",
        "BG_BUBBLE": "#1f0a0d",
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
    global PINK, PINK_SOFT, BG_DARK, BG_PANEL, BG_BUBBLE, _current_scheme_name
    scheme = THEMES[name]
    PINK = scheme["PINK"]
    PINK_SOFT = scheme["PINK_SOFT"]
    BG_DARK = scheme["BG_DARK"]
    BG_PANEL = scheme["BG_PANEL"]
    BG_BUBBLE = scheme["BG_BUBBLE"]
    _current_scheme_name = name


_apply_scheme(_current_scheme_name)  # sets initial PINK, PINK_SOFT, etc.


def set_theme(name):
    """Switch the active color scheme. name: 'classic_pink' | 'violet_dusk' | 'crimson_night'."""
    if name not in THEMES:
        raise ValueError(f"Unknown theme '{name}'. Options: {list(THEMES)}")
    _apply_scheme(name)
    theme_signals.changed.emit()


def current_theme_name():
    return _current_scheme_name