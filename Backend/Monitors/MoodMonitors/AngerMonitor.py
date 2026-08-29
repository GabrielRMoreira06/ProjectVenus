"""
anger_monitor.py

Watches Venus's anger level. When it crosses the threshold, she reacts
silently by drawing a "dead pixel" somewhere on screen — no speech, no
audio, just a small passive-aggressive visual glitch.

Rearms once anger drops back below the threshold and rises again (same
pattern as UptimeMonitor's rearm-on-threshold-cross).
"""

from ai.MoodController import mood
from Orchestrator  import Category
from Monitors.BaseMonitor import BaseMonitor


class AngerMonitor(BaseMonitor):

    def __init__(self, orchestrator, interval=3600, anger_limit=70):
        super().__init__(orchestrator, interval)
        self.anger_limit = anger_limit
        self._already_alerted = False

    def check(self):
        if mood.anger < self.anger_limit:
            self._already_alerted = False
            return

        if self._already_alerted:
            return

        self._already_alerted = True
        self._fire()

    def _fire(self):
        print(f"[AngerMonitor] Anger at {mood.anger}, drawing a dead pixel.")

        # No Gemini call — but still goes through Orchestrator, so this
        # never collides (on the Unity side) with a speech/action that's
        # being delivered at the exact same moment. The dict shape
        # matches ResponseParser's output exactly, since it travels
        # through the same /response endpoint and VenusResponse class
        # on the Unity side.
        def builder():
            return {
                "text": "",
                "action": "DEADPIXEL",
                "mood_variant": None,
                "mood_shift": None,
                "memory_type": "NONE",
                "memory_text": "NONE",
                "memory_expire": "NONE",
                "image_query": "NONE",
                "audio_path": None,  # no text, nothing to speak
            }

        self.orchestrator.add(Category.MONITOR, builder)