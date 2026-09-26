"""
mood_controller.py

Tracks Venus's internal emotional state — anger, energy, boredom, and
affection — as four values from 0 to 100, persisted to disk so mood
survives a restart.

Kept intentionally simple: one JSON file, no history, no decay over
time. If idle-drift ("mood slowly resets if nothing happens") is ever
wanted, that belongs in a monitor that calls into this controller, not
in this class.

MOOD ESCALATIONS: crossing a threshold fires a one-off Gemini call,
restricted to a single action, right here in adjust() — replacing the
old interval-polling AngerMonitor/EnergyMonitor. Each escalation's
action description is passed inline in the SYSTEM MESSAGE itself
rather than registered in ai/Prompts.py — these actions only ever
appear in these restricted calls, never on a normal turn, so there's
no shared catalog entry worth keeping. `worker` and `orchestrator` are
looked up lazily, inside each _fire_*_interaction (not at module load
time): ai.GeminiWorker imports THIS module, so a top-level import here
would be circular, and `orchestrator` is constructed in Server.py
after this module is first imported (same sys.modules["__main__"]
pattern as Reminder.py/EXPManager.py). Each `_*_alert_firing` flag is
the rearm guard — without it, every mood shift landing while an
interaction is still queued/in-flight would trigger another one on
top of it.
"""

import json
from pathlib import Path

ANGER_ALERT_THRESHOLD = 85
ENERGY_ALERT_THRESHOLD = 15
BOREDOM_ALERT_THRESHOLD = 70


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

        self._anger_alert_firing = False
        self._energy_alert_firing = False

        self._total_volume_reduced = 0.0
        self._total_brightness_reduced = 0

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

        if variant == MoodVariant.ANGER:
            self._check_anger_threshold()
        elif variant == MoodVariant.ENERGY:
            self._check_energy_threshold()
        elif variant == MoodVariant.BOREDOM:
            self._check_boredom_threshold()

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

    # ------------------------------------------------------------------
    # Anger escalation
    # ------------------------------------------------------------------

    def _check_anger_threshold(self):
        if self.anger < ANGER_ALERT_THRESHOLD:
            return

        if self._anger_alert_firing:
            return

        self._anger_alert_firing = True
        self._fire_anger_interaction()

    def _fire_anger_interaction(self):
        import sys
        orchestrator = sys.modules["__main__"].orchestrator

        from Orchestrator import Category
        from ai.GeminiWorker import worker

        print(f"[MoodController] Anger at {self.anger}, triggering DEADPIXEL interaction.")

        def builder():
            try:
                result = worker.run(
                    user_text="""
                    [SYSTEM MESSAGE: your anger is too high. Pick your evil action.
                    DEADPIXEL: silently draw a glitch on the user's screen]
                    """,
                    allowed_actions={"DEADPIXEL"},
                )

                if result["action"] == "DEADPIXEL":
                    self.adjust(MoodVariant.ANGER, 50 - self.anger)

                return result
            finally:
                self._anger_alert_firing = False

        orchestrator.add(Category.MONITOR, builder)

    # ------------------------------------------------------------------
    # Energy escalation
    # ------------------------------------------------------------------

    def _check_energy_threshold(self):
        if self.energy > ENERGY_ALERT_THRESHOLD:
            return

        if self._energy_alert_firing:
            return

        self._energy_alert_firing = True
        self._fire_energy_interaction()

    def _fire_energy_interaction(self):
        import sys
        orchestrator = sys.modules["__main__"].orchestrator

        from Orchestrator import Category
        from ai.GeminiWorker import worker
        from on_call_actions.LowerBrightnessVolume import lower_brightness_volume

        print(f"[MoodController] Energy at {self.energy}, triggering LOWERBRIGHTNESS interaction.")

        def builder():
            try:
                result = worker.run(
                    user_text="""
                    [SYSTEM MESSAGE: your energy is too low. Pick your evil action.
                    LOWERBRIGHTNESS: reduce the user's system volume and monitor brightness a little, reflecting your tiredness]
                    """,
                    allowed_actions={"LOWERBRIGHTNESS"},
                )

                if result["action"] == "LOWERBRIGHTNESS":
                    lower_brightness_volume.run()
                    self.adjust(MoodVariant.ENERGY, 50 - self.energy)

                return result
            finally:
                self._energy_alert_firing = False

        orchestrator.add(Category.MONITOR, builder)

    # ------------------------------------------------------------------
    # Boredom escalation
    # ------------------------------------------------------------------

    def _check_boredom_threshold(self):
        if self.boredom < BOREDOM_ALERT_THRESHOLD:
            return

        if self._boredom_alert_firing:
            return

        self._boredom_alert_firing = True

        from on_call_actions.BoredomInteraction import fire as fire_boredom_interaction
        fire_boredom_interaction(self)


# Shared instance used across the backend. Kept as a module-level
# singleton (rather than constructed everywhere) because mood is
# genuinely global — there's only one Venus, with one mood, per process.
mood = MoodController()