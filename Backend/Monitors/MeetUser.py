"""
MeetUser.py

Periodically asks the user a question to get to know them better.
Its real purpose is to resend the full context (memories, rules
explanation, format) to Gemini in a safe, low-stakes interaction.
"""

from ai.core.GeminiWorker import worker
from Orchestrator import Category
from Monitors.BaseMonitor import BaseMonitor


class MeetUserMonitor(BaseMonitor):

    def __init__(self, orchestrator, interval=7200):
        super().__init__(orchestrator, interval)

    def check(self):
        self._fire()

    def _fire(self):
        print("[MeetUserMonitor] Asking the user a getting-to-know-you question.")

        def builder():
            return worker.run(
                user_text="[SYSTEM MESSAGE: Ask a question to get to know the user better.]",
                full_context=True,
            )

        self.orchestrator.add(Category.MONITOR, builder)