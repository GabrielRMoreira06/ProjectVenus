"""
IgnoreTracker.py

Silently counts every message in the session (both sides) and how many
Venus messages in a row went unanswered. Subscribes to ChatHistory, so
nothing else has to call into it.

A user message resets the unanswered streak. While the user keeps
ignoring Venus, one SYSTEM message is sent to Gemini every
UNANSWERED_LIMIT unanswered messages (5, 10, 15, ...). The count is
never restarted until the user answers.
"""

import sys
import threading

from ai.ChatHistory import chat_history

UNANSWERED_LIMIT = 5


class IgnoreTracker:

    def __init__(self, limit=UNANSWERED_LIMIT):
        self.limit = limit
        self.total_messages = 0
        self.unanswered = 0

        self._lock = threading.Lock()

        chat_history.subscribe(self._on_message)

    def _on_message(self, message):
        should_fire = False

        with self._lock:
            self.total_messages += 1

            if message["role"] == "user":
                self.unanswered = 0
                return

            self.unanswered += 1

            if self.unanswered > self.limit and (self.unanswered - 1) % self.limit == 0:
                should_fire = True
                count = self.unanswered

        if should_fire:
            self._fire(count)

    def _fire(self, count):
        orchestrator = sys.modules["__main__"].orchestrator

        from Orchestrator import Category
        from ai.core.GeminiWorker import worker

        print(f"[IgnoreTracker] {count} unanswered messages, alerting.")

        def builder():
            return worker.run(
                user_text=f"[SYSTEM MESSAGE: {count} unanswered messages, user is ignoring you.]"
            )

        orchestrator.add(Category.SYSTEM, builder)


ignore_tracker = IgnoreTracker()