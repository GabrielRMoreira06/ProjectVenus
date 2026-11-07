"""
MeetUser.py

Silently counts every message in the session (both sides) by
subscribing to ChatHistory, so nothing else has to call into it. Every
MESSAGES_PER_QUESTION messages (20, 40, 60, ...), it waits
DELAY_SECONDS and then sends one SYSTEM message asking Venus to ask the
user a getting-to-know-you question.

Its real purpose is to resend the full context (memories, rules
explanation, format) to Gemini in a safe, low-stakes interaction.
"""

import sys
import threading

from ai.ChatHistory import chat_history

MESSAGES_PER_QUESTION = 20
DELAY_SECONDS = 60


class MeetUserTracker:

    def __init__(self, messages_per_question=MESSAGES_PER_QUESTION, delay=DELAY_SECONDS):
        self.messages_per_question = messages_per_question
        self.delay = delay
        self.total_messages = 0

        self._lock = threading.Lock()

        chat_history.subscribe(self._on_message)

    def _on_message(self, message):
        with self._lock:
            self.total_messages += 1
            should_fire = self.total_messages % self.messages_per_question == 0
            count = self.total_messages

        if should_fire:
            print(f"[MeetUserTracker] {count} messages, asking in {self.delay}s.")
            timer = threading.Timer(self.delay, self._fire)
            timer.daemon = True
            timer.start()

    def _fire(self):
        orchestrator = sys.modules["__main__"].orchestrator

        from Orchestrator import Category
        from ai.core.GeminiWorker import worker

        print("[MeetUserTracker] Asking the user a getting-to-know-you question.")

        def builder():
            return worker.run(
                user_text="[SYSTEM MESSAGE: Ask a question to get to know the user better.]",
                full_context=True,
            )

        orchestrator.add(Category.SYSTEM, builder)


meet_user_tracker = MeetUserTracker()