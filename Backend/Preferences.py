"""
Preferences.py

Persists which "interactions" — passive monitors and Gemini-decided
ACTIONS — are enabled, and at what interval the monitors poll. Same
pattern as MoodController/MemoryManager: one JSON file, loaded once,
rewritten on every change.

Two kinds of interaction, because they're controlled differently:
  - MONITORS: background threads with a real polling interval (see
    Monitors/BaseMonitor.py). Both `enabled` and `interval` apply, and
    take effect live — BaseMonitor reads both fresh every loop
    iteration, so PassiveMonitor just has to update the attributes.
  - ACTIONS: things Gemini can choose to do in a normal response (see
    ai/Prompts.py). There's no polling interval — Gemini decides
    per-turn — so only `enabled` applies. Disabling one removes it
    from the prompt entirely the next time GeminiWorker builds one.

id -> (label, description, default_interval_seconds) for monitors,
id -> (label, description) for actions. These double as the catalog
PanelWindow's Preferences tab renders rows from.
"""

import json
from pathlib import Path

MONITOR_CATALOG = {
    "boredom": (
        "Boredom comments",
        "Comments on a random image from your Downloads folder when she's bored enough.",
        3000,
    ),
    "hardware": (
        "Hardware alerts",
        "Flags it when overall CPU or RAM usage crosses the limit.",
        900,
    ),
    "uptime": (
        "Uptime nagging",
        "Comments when your PC has been on for a long stretch without a restart.",
        72000,
    ),
    "process": (
        "Process alerts",
        "Flags a single process hogging CPU or RAM.",
        3600,
    ),
    "anger": (
        "Anger glitch",
        "Draws a silent 'dead pixel' glitch on screen when her anger is high.",
        3600,
    ),
    "energy": (
        "Low-energy dimming",
        "Nudges system volume and monitor brightness down a little when her energy is low.",
        5000,
    ),
    "screenpeek": (
        "Screen peeking",
        "Periodically takes a look at your screen and comments on it.",
        1200,
    ),
    "generic_interaction": (
        "Idle chatter",
        "Asks you something or comments on an open window when nothing else has happened in a while.",
        2000,
    ),
    "email": (
        "Email checking",
        "Checks your inbox for new emails and comments on them.",
        120,
    ),
}

ACTION_CATALOG = {
    "KEYBOARDCONTROL": ("Keyboard control", "Types on your keyboard directly."),
    "OPENIMAGE": ("Open image", "Shows an image pulled from the internet alongside her text."),
    "ALLOWPET": ("Allow pet", "Lets you pet her head with a draggable hand."),
    "FINDFILE": ("Find file", "Searches your computer for a file and opens it in Explorer."),
    "STEALMOUSE": ("Steal mouse", "Tugs your cursor toward the close button, like she's fighting for control."),
    "SCREAM": ("Scream", "Distorts her voice into a harsh, blown-out scream for one line."),
    "REMINDER": ("Reminders", "Sets a timed reminder that she brings up again later."),
}


class Preferences:

    def __init__(self, file_path="preferences.json"):
        self.file_path = Path(file_path)
        state = self._load()

        self.monitors = {}
        for monitor_id, (_, _, default_interval) in MONITOR_CATALOG.items():
            saved = state.get("monitors", {}).get(monitor_id, {})
            self.monitors[monitor_id] = {
                "enabled": saved.get("enabled", True),
                "interval": saved.get("interval", default_interval),
            }

        self.actions = {}
        for action_id in ACTION_CATALOG:
            saved = state.get("actions", {}).get(action_id, {})
            self.actions[action_id] = {"enabled": saved.get("enabled", True)}

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
        state = {"monitors": self.monitors, "actions": self.actions}
        with open(self.file_path, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=4)

    def subscribe(self, listener):
        """
        listener(kind, item_id) is called after any change — kind is
        "monitor" or "action". PassiveMonitor uses this to push
        enabled/interval changes into the actual running monitor
        threads without a restart.
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

    def get_monitor_interval(self, monitor_id):
        return self.monitors.get(monitor_id, {}).get(
            "interval", MONITOR_CATALOG[monitor_id][2]
        )

    def set_monitor_enabled(self, monitor_id, enabled):
        self.monitors[monitor_id]["enabled"] = enabled
        self._save()
        self._notify("monitor", monitor_id)

    def set_monitor_interval(self, monitor_id, interval_seconds):
        self.monitors[monitor_id]["interval"] = int(interval_seconds)
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


# Shared instance, same pattern as `mood`/`worker` elsewhere.
preferences = Preferences()