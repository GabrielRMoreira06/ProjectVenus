"""
EXPManager.py

Tracks Venus's XP and level across sessions, persisted to disk — same
pattern as MoodController/MemoryManager/Preferences: one JSON file,
loaded once, rewritten on every change.

`add_xp()` is the only thing callers need to know about. Server.py
calls it once per interaction, from the same spot that already marks
OneTimeManager's silence timer (queue_response) — any response that
actually reached Unity (user turn, monitor comment, system message)
counts as "an interaction" for XP purposes, same definition
mark_interaction() already uses.

When accumulated XP crosses the threshold for the next level (there
can be more than one level in a single add_xp() call, e.g. a big XP
grant or a low threshold — handled with a while loop, not an if),
level-up fires on its OWN background thread:
  - an AI-generated image marking the level-up is saved to the user's
    Pictures folder. Generation goes through Gemini's interactions API
    directly (client.interactions.create(model="gemini-3.1-flash-image",
    ...)) rather than the Imagen-specific generate_images() endpoint —
    output_image.data comes back base64-encoded, decoded before being
    written to disk.
  - a `[SYSTEM MESSAGE: Level up, you're now level {level}]` is
    submitted through Orchestrator (Category.SYSTEM), so Venus reacts
    to it in her own voice — same pipeline shape as every other
    monitor/check (builder -> Orchestrator -> GeminiWorker).

Like Reminder.py's firing functions, `orchestrator` is looked up
lazily via sys.modules["__main__"] rather than imported at module
load time — Server.py imports this (indirectly, via queue_response)
before `orchestrator` is constructed, so a top-level import would be
circular. Running on its own thread also means a slow image-gen call
never blocks whatever thread called add_xp() (a Flask request thread
or Orchestrator's own worker thread, depending on the caller).
"""

import base64
import json
import threading
from datetime import datetime
from pathlib import Path

from google import genai

from config import GEMINI_KEY

IMAGE_MODEL_NAME = "gemini-3.1-flash-image"

DEFAULT_XP_PER_INTERACTION = 25

# xp required to go from `level` to `level + 1`. Deliberately simple —
# a mild exponential curve rather than a full RPG leveling formula.
XP_BASE = 100
XP_GROWTH = 1.25


class ExpManager:

    def __init__(self, file_path="exp_state.json", skip_image_generation=True):
        self.file_path = Path(file_path)
        state = self._load()

        self.level = state.get("level", 1)
        # XP accumulated toward the NEXT level — resets (with the
        # overflow carried forward) on every level up, it's not a
        # lifetime total.
        self.xp = state.get("xp", 0)

        # Mirrors TTSWorker's skip_synthesis flag — the Gemini image
        # API needs billing enabled on the account, which isn't set up
        # yet. Level-up still fires the SYSTEM MESSAGE normally; only
        # the image-generation call is skipped. Flip to False (or pass
        # skip_image_generation=False at construction) once billing is
        # in place.
        self.skip_image_generation = skip_image_generation

        self._lock = threading.Lock()
        self._client = None  # lazy — see _get_client()

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
        """Returns (current_xp, xp_needed) for the CURRENT level — what a progress bar wants."""
        return self.xp, self.xp_to_next_level()

    def add_xp(self, amount=DEFAULT_XP_PER_INTERACTION):
        """
        Adds `amount` xp and handles any resulting level-up(s). Returns
        True if at least one level-up happened this call.
        """
        with self._lock:
            self.xp += amount
            leveled_up = False

            while self.xp >= self.xp_to_next_level():
                self.xp -= self.xp_to_next_level()
                self.level += 1
                leveled_up = True

            self._save()
            new_level = self.level

        if leveled_up:
            print(f"[ExpManager] Leveled up to {new_level}!")
            threading.Thread(
                target=self._fire_level_up, args=(new_level,), daemon=True
            ).start()

        return leveled_up

    # ------------------------------------------------------------------
    # Level-up side effects
    # ------------------------------------------------------------------

    def _fire_level_up(self, level):
        self._generate_level_up_image(level)

        import sys
        orchestrator = sys.modules["__main__"].orchestrator

        from Orchestrator import Category
        from ai.GeminiWorker import worker

        def builder():
            return worker.run(user_text=f"[SYSTEM MESSAGE: Level up, you're now level {level}]")

        orchestrator.add(Category.SYSTEM, builder)

    def _get_client(self):
        if self._client is None:
            self._client = genai.Client(api_key=GEMINI_KEY)
        return self._client

    def _generate_level_up_image(self, level):
        if self.skip_image_generation:
            print(f"[ExpManager] Image generation disabled (no billing yet) — skipping level {level} image.")
            return

        try:
            prompt = (
                f"Create a celebratory piece of digital art marking a virtual "
                f"desktop companion named Venus leveling up to level {level}. "
                f"Pink and dark color palette, sparkles and light effects, no "
                f"readable text."
            )

            interaction = self._get_client().interactions.create(
                model=IMAGE_MODEL_NAME,
                input=prompt,
            )

            image_bytes = base64.b64decode(interaction.output_image.data)

            pictures_dir = Path.home() / "Pictures"
            pictures_dir.mkdir(parents=True, exist_ok=True)

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_path = pictures_dir / f"venus_levelup_{level}_{timestamp}.png"
            output_path.write_bytes(image_bytes)

            print(f"[ExpManager] Level-up image saved to '{output_path}'.")

        except Exception:
            import traceback
            traceback.print_exc()


# Shared instance, same pattern as `mood`/`worker`/`preferences` elsewhere.
# skip_image_generation defaults to True — see the note in __init__.
exp_manager = ExpManager()