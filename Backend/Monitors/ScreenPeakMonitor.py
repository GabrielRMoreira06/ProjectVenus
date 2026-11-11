"""
screen_peek_monitor.py

When it gets a turn, Venus takes a peek at the user's screen and
comments on what she sees. Unlike most monitors, this one doesn't
depend on any threshold — it always fires when it's its turn.
"""

from ai.tools.ScreenCapture import capture_screen
from ai.core.GeminiWorker import worker
from Orchestrator import Category
from Monitors.BaseMonitor import BaseMonitor


class ScreenPeekMonitor(BaseMonitor):

    def __init__(self, orchestrator, pace=4):
        super().__init__(orchestrator, pace)

    def check(self):
        self._fire()
        return True

    def _fire(self):
        print("[ScreenPeekMonitor] Peeking at the user's screen.")

        # The capture happens INSIDE builder(), so it only takes the
        # screenshot once it's actually this request's turn — if it
        # sits in the queue for a while, the image sent is still
        # current, not a stale photo taken at enqueue time.
        def builder():
            image = capture_screen()
            return worker.run(
                user_text="[SYSTEM MESSAGE: You are looking at the user's screen right now. Comment on the content.]",
                image=image,
            )

        self.orchestrator.add(Category.MONITOR, builder)