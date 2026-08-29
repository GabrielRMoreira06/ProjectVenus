"""
screen_peek_monitor.py

Every `interval`, Venus takes a peek at the user's screen and comments
on what she sees. Unlike most monitors, this one doesn't depend on any
threshold — it fires purely on a timer, subject only to Orchestrator's
global cooldown and priority.
"""

from ai.ScreenCapture import capture_screen
from ai.GeminiWorker import worker
from Orchestrator import Category
from Monitors.BaseMonitor import BaseMonitor


class ScreenPeekMonitor(BaseMonitor):

    def __init__(self, orchestrator, interval=1200):
        super().__init__(orchestrator, interval)

    def check(self):
        self._fire()

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