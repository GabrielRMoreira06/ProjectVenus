"""
Preferences.py

Persists which "interactions" — passive monitors and Gemini-decided
ACTIONS — are enabled, and each monitor's pace. Also persists
standalone app settings (voice volume, effects) that aren't tied to a
monitor or action. Same pattern as MoodController/MemoryManager: one
JSON file, loaded once, rewritten on every change.

Two kinds of interaction, because they're controlled differently:
  - MONITORS: scheduled by PassiveMonitor's single global idle
    cooldown (IDLE_COOLDOWN_SECONDS). Each has `enabled` and a `pace`
    — the number of cooldowns between its turns. Both take effect
    live, PassiveMonitor just has to update the attributes. Entries
    with a default pace of None aren't scheduled by the cooldown at
    all (they're driven by mood or message count), so they have no
    pace.
  - ACTIONS: things Gemini can choose to do in a normal response (see
    ai/Prompts.py). There's no scheduling — Gemini decides per-turn —
    so only `enabled` applies. Disabling one removes it from the
    prompt entirely the next time GeminiWorker builds one.

SETTINGS: plain key/value app settings with no catalog — no
enable/pace split needed, just a value each.

id -> (label, description, default_pace) for monitors, id -> (label,
description) for actions. These double as the catalog PanelWindow's
Preferences tab renders rows from.
"""

import json
from pathlib import Path
from config import STATE_DIR

# One global cooldown: this many seconds without any chat message
# (either side) = one cooldown elapsed = at most one monitor fires.
IDLE_COOLDOWN_SECONDS = 300

MONITOR_CATALOG = {
    "boredom": (
        "Boredom comments",
        "Comments on a random image from your Downloads folder when she's bored enough.",
        None,
    ),
    "hardware": (
        "Hardware alerts",
        "Flags it when overall CPU or RAM usage crosses the limit.",
        3,
    ),
    "uptime": (
        "Uptime nagging",
        "Comments when your PC has been on for a long stretch without a restart.",
        12,
    ),
    "process": (
        "Process alerts",
        "Flags a single process hogging CPU or RAM.",
        12,
    ),
    "screenpeek": (
        "Screen peeking",
        "Periodically takes a look at your screen and comments on it.",
        4,
    ),
    "generic_interaction": (
        "Idle chatter",
        "Asks you something or comments on an open window when nothing else has happened in a while.",
        7,
    ),
    "email": (
        "Email checking",
        "Checks your inbox for new emails and comments on them.",
        1,
    ),
    "meetuser": (
        "Getting to know you",
        "Occasionally asks you a question to learn more about you.",
        None,
    ),
}

ACTION_CATALOG = {
    "KEYBOARDCONTROL": ("Keyboard control", "Types on your keyboard directly."),
    "SHOWIMAGE": ("Open image", "Shows an image pulled from the internet alongside her text."),
    "ALLOWPET": ("Allow pet", "Lets you pet her head with a draggable hand."),
    "FINDFILE": ("Find file", "Searches your computer for a file and opens it in Explorer."),
    "STEALMOUSE": ("Steal mouse", "Tugs your cursor toward the close button, like she's fighting for control."),
    "SCREAM": ("Scream", "Distorts her voice into a harsh, blown-out scream for one line."),
    "REMINDER": ("Reminders", "Sets a timed reminder that she brings up again later."),
    "FLIP": ("Flip", "Spins her whole body 360 degrees clockwise."),
    "JUDGE": ("Judge stare", "Moves in close to stare at you for a moment."),
    "CLEANDISK": ("Clean disk", "Deletes temp files to free up disk space."),
    "ORGANIZEFILES": ("Organize downloads", "Sorts loose files in your Downloads folder into subfolders by type."),
    "NOTEPAD": ("Notepad", "Reads what's written in your notepad, and can rewrite its content."),
    "DICE": ("Dice roll", "Rolls a physical die on screen and reports what it landed on."),
    "INTERNETCHECK": ("Internet check", "Tests your ping, download and upload speed."),
}

DEFAULT_VOICE_VOLUME = 100
DEFAULT_ROBOTIC_EFFECT = True
DEFAULT_START_WITH_WINDOWS = False


class Preferences:

    def __init__(self, file_path=STATE_DIR / "preferences.json"):
        self.file_path = Path(file_path)
        state = self._load()

        # Old files stored a per-monitor "interval" in seconds; it's
        # simply ignored here and dropped on the next save.
        self.monitors = {}
        for monitor_id, (_, _, default_pace) in MONITOR_CATALOG.items():
            saved = state.get("monitors", {}).get(monitor_id, {})
            self.monitors[monitor_id] = {
                "enabled": saved.get("enabled", True),
                "pace": saved.get("pace", default_pace),
            }

        self.actions = {}
        for action_id in ACTION_CATALOG:
            saved = state.get("actions", {}).get(action_id, {})
            self.actions[action_id] = {"enabled": saved.get("enabled", True)}

        saved_settings = state.get("settings", {})
        self.settings = {
            "voice_volume": saved_settings.get("voice_volume", DEFAULT_VOICE_VOLUME),
            "robotic_effect": saved_settings.get("robotic_effect", DEFAULT_ROBOTIC_EFFECT),
            "start_with_windows": saved_settings.get("start_with_windows", DEFAULT_START_WITH_WINDOWS),
        }

        self._listeners = []

    def _load(self):
        if not self.file_path.exists():
            return {}

        try:
            with open(self.file_path, "r", encoding="utf-8") as f:
                content = f.read().strip()
                return json.loads(content) if content else {}
        except (json.JSONDecodeError, OSError):
            print(f"[Preferences] '{self.file_path}' is empty or corrupted — starting with defaults.")
            return {}

    def _save(self):
        state = {"monitors": self.monitors, "actions": self.actions, "settings": self.settings}
        with open(self.file_path, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=4)

    def subscribe(self, listener):
        """
        listener(kind, item_id) is called after any change — kind is
        "monitor", "action", or "setting". PassiveMonitor uses this to
        push enabled/pace changes into the monitors without a restart.
        """
        self._listeners.append(listener)

    def _notify(self, kind, item_id):
        for listener in self._listeners:
            listener(kind, item_id)

    # ------------------------------------------------------------------
    # Monitors
    # ------------------------------------------------------------------

    def is_monitor_enabled(self, monitor_id):
        return self.monitors.get(monitor_id, {}).get("enabled", True)

    def get_monitor_pace(self, monitor_id):
        """Cooldowns between this monitor's turns, or None if it isn't paced."""
        return self.monitors.get(monitor_id, {}).get("pace", MONITOR_CATALOG[monitor_id][2])

    def set_monitor_enabled(self, monitor_id, enabled):
        self.monitors[monitor_id]["enabled"] = enabled
        self._save()
        self._notify("monitor", monitor_id)

    def set_monitor_pace(self, monitor_id, pace):
        self.monitors[monitor_id]["pace"] = max(1, int(pace))
        self._save()
        self._notify("monitor", monitor_id)

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def is_action_enabled(self, action_id):
        return self.actions.get(action_id, {}).get("enabled", True)

    def enabled_actions(self):
        """Used by ai/Prompts.py to build the ACTION list/explanation Gemini sees."""
        return {
            action_id for action_id, state in self.actions.items()
            if state.get("enabled", True)
        }

    def set_action_enabled(self, action_id, enabled):
        self.actions[action_id]["enabled"] = enabled
        self._save()
        self._notify("action", action_id)

    # ------------------------------------------------------------------
    # Settings
    # ------------------------------------------------------------------

    def get_voice_volume(self):
        return self.settings.get("voice_volume", DEFAULT_VOICE_VOLUME)

    def set_voice_volume(self, percent):
        self.settings["voice_volume"] = max(0, min(100, int(percent)))
        self._save()
        self._notify("setting", "voice_volume")

    def is_robotic_effect_enabled(self):
        return self.settings.get("robotic_effect", DEFAULT_ROBOTIC_EFFECT)

    def set_robotic_effect_enabled(self, enabled):
        self.settings["robotic_effect"] = bool(enabled)
        self._save()
        self._notify("setting", "robotic_effect")

    def is_start_with_windows_enabled(self):
        return self.settings.get("start_with_windows", DEFAULT_START_WITH_WINDOWS)

    def set_start_with_windows_enabled(self, enabled):
        self.settings["start_with_windows"] = bool(enabled)
        self._save()
        self._notify("setting", "start_with_windows")


# Shared instance, same pattern as `mood`/`worker` elsewhere.
preferences = Preferences()