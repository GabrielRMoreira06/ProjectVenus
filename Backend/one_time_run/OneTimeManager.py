"""
one_time_manager.py

Runs "once per session" checks (hardware specs, disk space, memory
cleanup, ...) without competing with the boot message or anything else
that just happened. Instead of running everything at boot — which
would stack on top of the boot message — this waits for a period of
silence (no interaction of any kind) before running whatever checks
are still pending.

Each check runs at most once per session, whether or not it produced a
response (marked as done either way, so it's never re-checked). Only
one response is delivered per silence window, so a long idle period
doesn't dump two checks on the user back-to-back.

Each check object exposes `check()`, which does only the CHEAP work
(collect data, compare to last known state) and returns a PROMPT
string, or None if there's nothing to report — it never talks to
Gemini directly. This manager wraps that prompt into a builder and
hands it to Orchestrator, which is the one place that actually decides
when the Gemini call happens.
"""

import threading
import time

from ai.GeminiWorker import worker
from Orchestrator import Category


class OneTimeManager:

    def __init__(self, orchestrator, checks=None, silence_duration=300, poll_interval=15):
        self.orchestrator = orchestrator
        self.checks = checks or []
        self.silence_duration = silence_duration
        self.poll_interval = poll_interval

        self._interaction_lock = threading.Lock()
        self._last_interaction = time.time()

        self._already_run = set()
        self._running = False

    def mark_interaction(self):
        """
        Called whenever anything happens (user question, spontaneous
        action, boot) — resets the silence timer.
        """
        with self._interaction_lock:
            self._last_interaction = time.time()

    def _silence_is_long_enough(self):
        with self._interaction_lock:
            return time.time() - self._last_interaction >= self.silence_duration

    def start(self):
        self._running = True
        threading.Thread(target=self._loop, daemon=True, name="OneTimeManager").start()

    def stop(self):
        self._running = False

    def _loop(self):
        # COM needs to be initialized on THIS thread before any WMI call
        # (used by HardwareInspect) — without this, WMI fails with
        # "you're probably running inside a thread without first calling
        # pythoncom.CoInitialize[Ex]".
        import pythoncom
        pythoncom.CoInitialize()

        try:
            while self._running:
                time.sleep(self.poll_interval)

                if not self._silence_is_long_enough():
                    continue

                self._run_pending()
        finally:
            pythoncom.CoUninitialize()

    def _run_pending(self):
        for check in self.checks:
            name = check.__class__.__name__

            if name in self._already_run:
                continue

            self._already_run.add(name)

            try:
                prompt = check.check()
            except Exception:
                import traceback
                traceback.print_exc()
                continue

            if prompt is not None:
                print(f"[OneTimeManager] '{name}' produced a response, delivering.")

                def builder(p=prompt):
                    return worker.run(user_text=p)

                self.orchestrator.add(Category.SYSTEM, builder)
                self.mark_interaction()
                return  # only one per silence window; the rest wait for the next