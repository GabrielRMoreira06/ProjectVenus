"""
mood_controller.py

Tracks Venus's internal emotional state — anger, energy, boredom, and
affection — as four values from 0 to 100, persisted to disk so mood
survives a restart.

Kept intentionally simple: one JSON file, no history, no decay over
time. If idle-drift ("mood slowly resets if nothing happens") is ever
wanted, that belongs in a monitor that calls into this controller, not
in this class.
"""

import json
from pathlib import Path


class MoodVariant:
    ANGER = "ANGER"
    ENERGY = "ENERGY"
    BOREDOM = "BOREDOM"
    AFFECTION = "AFFECTION"

    ALL = (ANGER, ENERGY, BOREDOM, AFFECTION)


class MoodShift:
    INCREASE = "INCREASE"
    DECREASE = "DECREASE"
    NONE = "NONE"


class MoodController:

    DEFAULT_VALUE = 50

    def __init__(self, file_path="mood_state.json"):
        self.file_path = Path(file_path)

        state = self._load()

        # One attribute per variant, lowercase (self.anger, self.energy, ...)
        for variant in MoodVariant.ALL:
            setattr(self, variant.lower(), state.get(variant.lower(), self.DEFAULT_VALUE))

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
            print(f"[MoodController] '{self.file_path}' is empty or corrupted — starting with default mood.")
            return {}

    def _save(self):
        state = {variant.lower(): getattr(self, variant.lower()) for variant in MoodVariant.ALL}

        with open(self.file_path, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=4)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_prompt(self):
        return f"""
Venus Current emotional state:

Anger: {self.anger}/100
Energy: {self.energy}/100
Boredom: {self.boredom}/100
Affection: {self.affection}/100

These values represent your internal emotions.
Let them influence your behavior naturally.
Do not mention the numbers.
"""

    def adjust(self, variant, amount):
        """
        Moves the given variant by `amount` (positive or negative),
        clamped to [0, 100]. This is the single place mood values
        actually change — increase/decrease are just adjust() with a
        sign, instead of eight near-duplicate methods.
        """
        if variant not in MoodVariant.ALL:
            print(f"[MoodController] Unknown mood variant: '{variant}' — ignoring.")
            return

        attribute = variant.lower()
        current = getattr(self, attribute)
        new_value = max(0, min(100, current + amount))

        setattr(self, attribute, new_value)
        self._save()

    def apply_shift(self, variant, shift, amount=8):
        """
        Applies a MOOD_SHIFT (INCREASE/DECREASE/NONE) to the attribute
        named by MOOD_VARIANT, as parsed from the Gemini response.

        `amount` is kept small on purpose — MOOD_SHIFT can happen on
        almost every interaction, so large jumps would make the mood
        swing too fast to feel natural.
        """
        if not variant or not shift or shift == MoodShift.NONE:
            return

        if shift == MoodShift.INCREASE:
            self.adjust(variant, amount)
        elif shift == MoodShift.DECREASE:
            self.adjust(variant, -amount)
        else:
            print(f"[MoodController] Unknown mood shift: '{shift}' — ignoring.")


# Shared instance used across the backend. Kept as a module-level
# singleton (rather than constructed everywhere) because mood is
# genuinely global — there's only one Venus, with one mood, per process.
mood = MoodController()