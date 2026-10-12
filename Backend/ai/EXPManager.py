"""
EXPManager.py

Tracks Venus's XP and level across sessions, persisted to disk — same
pattern as MoodController/MemoryManager/Preferences: one JSON file,
loaded once, rewritten on every change.

`add_xp()` is the only thing callers need to know about. Server.py
calls it once per interaction, from queue_response.

UNLOCKS: completing level N (levelling up from N to N+1) unlocks the
entry keyed N. Anything not listed in UNLOCKS is available from the
start. Unlock state is derived from the current level, so nothing
extra is persisted.

On level-up, a background thread submits one SYSTEM message per level
gained through Orchestrator. If a level carried an unlock, the message
names it, and an unlocked monitor is triggered immediately via
PassiveMonitor.

`orchestrator` and `passive_monitor` are looked up lazily via
sys.modules["__main__"] — Server.py constructs them after this module
is imported.
"""

import json
import threading
from pathlib import Path

from config import STATE_DIR
from Preferences import MONITOR_CATALOG

DEFAULT_XP_PER_INTERACTION = 25

XP_BASE = 100
XP_GROWTH = 1.25

UNLOCKS = {
    1: ("action", "STEALMOUSE"),
    2: ("action", "FLIP"),
    3: ("monitor", "screenpeek"),
    4: ("action", "JUDGE"),
    5: ("action", "SHOWIMAGE"),
    6: ("monitor", "uptime"),
    7: ("action", "SCREAM"),
    8: ("action", "DICE"),
    9: ("monitor", "process"),
    10: ("action", "ORGANIZEFILES"),
    11: ("action", "ALLOWPET"),
    12: ("monitor", "generic_interaction"),
}

_UNLOCK_LEVEL = {entry: level for level, entry in UNLOCKS.items()}


class ExpManager:

    def __init__(self, file_path=STATE_DIR / "exp_state.json"):
        self.file_path = Path(file_path)
        state = self._load()

        self.level = state.get("level", 1)
        self.xp = state.get("xp", 0)

        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _load(self):
        if not self.file_path.exists():
            return {}

        try:
            with open(self.file_path, "r", encoding="utf-8") as f:
                content = f.read().strip()
                return json.loads(content) if content else {}
        except (json.JSONDecodeError, OSError):
            print(f"[ExpManager] '{self.file_path}' is empty or corrupted — starting at level 1.")
            return {}

    def _save(self):
        state = {"level": self.level, "xp": self.xp}
        with open(self.file_path, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=4)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def xp_to_next_level(self, level=None):
        level = self.level if level is None else level
        return int(XP_BASE * (XP_GROWTH ** (level - 1)))

    def progress(self):
        """Returns (current_xp, xp_needed) for the CURRENT level."""
        return self.xp, self.xp_to_next_level()

    def is_unlocked(self, kind, item_id):
        """kind: "action" or "monitor". Items not in UNLOCKS are always unlocked."""
        required_level = _UNLOCK_LEVEL.get((kind, item_id))

        if required_level is None:
            return True

        return self.level > required_level

    def add_xp(self, amount=DEFAULT_XP_PER_INTERACTION):
        """
        Adds `amount` xp and handles any resulting level-up(s). Returns
        True if at least one level-up happened this call.
        """
        with self._lock:
            old_level = self.level
            self.xp += amount

            while self.xp >= self.xp_to_next_level():
                self.xp -= self.xp_to_next_level()
                self.level += 1

            self._save()
            new_level = self.level

        leveled_up = new_level > old_level

        if leveled_up:
            print(f"[ExpManager] Leveled up to {new_level}!")
            threading.Thread(
                target=self._fire_level_up, args=(old_level, new_level), daemon=True
            ).start()

        return leveled_up

    # ------------------------------------------------------------------
    # Level-up side effects
    # ------------------------------------------------------------------

    def _fire_level_up(self, old_level, new_level):
        import sys
        main = sys.modules["__main__"]
        orchestrator = main.orchestrator

        from Orchestrator import Category
        from ai.core.GeminiWorker import worker

        for completed_level in range(old_level, new_level):
            reached_level = completed_level + 1
            unlock = UNLOCKS.get(completed_level)

            if unlock is None:
                message = f"[SYSTEM MESSAGE: Level up, you're now level {reached_level}]"
            else:
                kind, item_id = unlock
                name = MONITOR_CATALOG[item_id][0] if kind == "monitor" else item_id
                message = f"[SYSTEM MESSAGE: Level up, you're now level {reached_level} and unlocked {name}]"

            def builder(m=message):
                return worker.run(user_text=m)

            orchestrator.add(Category.SYSTEM, builder)

            if unlock is not None and unlock[0] == "monitor":
                main.passive_monitor.unlock_monitor(unlock[1])


exp_manager = ExpManager()