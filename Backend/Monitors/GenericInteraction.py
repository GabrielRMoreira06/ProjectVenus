"""
generic_interaction.py

A monitor with no metric to watch — it exists purely to vary the kind
of thing Venus says when nothing else has happened in a while. Two
behaviors: ask the user something, or comment on one of their open
windows.

This is the reference example of the full pipeline every monitor
should follow:

  1. INTERNAL COOLDOWN — BaseMonitor's own `interval` timer decides
     when this monitor is even allowed to consider firing again.
  2. ORCHESTRATOR — `check()` never calls Gemini itself. It builds a
     zero-argument `builder` function and hands it to
     `orchestrator.add(category, builder)`. From there, Orchestrator
     decides WHEN builder() actually runs, based on priority
     (Category) and the GLOBAL cooldown (min_delivery_spacing) shared
     across every monitor and the user.
  3. GEMINI WORKER — when it's this request's turn, builder() calls
     `worker.run(...)`, which sends the message to the ongoing Gemini
     chat session.
  4. RESPONSE PARSER — `worker.run()` already parses the raw model
     text into a structured dict before returning it. Nothing here
     touches ResponseParser directly — that's an implementation detail
     of GeminiWorker, not of the monitor.
  5. SEND TO UNITY — builder()'s return value is handed to
     Orchestrator's `on_result` callback, wired up once in server.py to
     queue the response for Unity to pick up. This monitor never talks
     to Unity, or even needs to know delivery exists.
"""

import ctypes
import random

from ai.GeminiWorker import worker
from Orchestrator import Category
from Monitors.BaseMonitor import BaseMonitor

EXCLUDED_TITLES = {"Program Manager", "Windows Input Experience"}


def get_open_windows():
    """
    Returns the titles of every visible open window on the system —
    gives Gemini a list of "things it could comment on". Only titles,
    never window content (that was tried via pywinauto and dropped:
    poor results on most modern apps, which don't expose content
    through Windows accessibility APIs).
    """
    windows = []

    def callback(hwnd, lparam):
        if not ctypes.windll.user32.IsWindowVisible(hwnd):
            return True

        length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
        if length == 0:
            return True

        buffer = ctypes.create_unicode_buffer(length + 1)
        ctypes.windll.user32.GetWindowTextW(hwnd, buffer, length + 1)
        title = buffer.value.strip()

        if title and title not in EXCLUDED_TITLES:
            windows.append(title)

        return True

    enum_windows_proc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_int, ctypes.c_int)
    ctypes.windll.user32.EnumWindows(enum_windows_proc(callback), 0)

    seen = set()
    return [w for w in windows if not (w in seen or seen.add(w))]


class GenericInteractionMonitor(BaseMonitor):

    def __init__(self, orchestrator, interval=2000):
        super().__init__(orchestrator, interval)

        self.behavior_weights = {
            "ask": 5,
            "inspect": 5,
        }

    def check(self):
        behavior = self._choose_behavior()

        if behavior == "inspect":
            self._fire_inspect()
        else:
            self._fire_ask()

    def _choose_behavior(self):
        behaviors = list(self.behavior_weights.keys())
        weights = list(self.behavior_weights.values())
        return random.choices(behaviors, weights=weights, k=1)[0]

    def _fire_ask(self):
        print("[GenericInteractionMonitor] Asking the user something.")

        def builder():
            return worker.run(    user_text="[SYSTEM MESSAGE: Browse the internet for a recent, interesting news and comment on it to User]")

        self.orchestrator.add(Category.MONITOR, builder)

    def _fire_inspect(self):
        windows = get_open_windows()

        if not windows:
            print("[GenericInteractionMonitor] No windows found, falling back to 'ask'.")
            self._fire_ask()
            return

        window_list = "\n".join(f"- {title}" for title in windows)
        prompt = f"""=== OPEN WINDOWS ===
{window_list}

[SYSTEM MESSAGE: Venus checked the open windows. Pick one and comment.]"""

        print("[GenericInteractionMonitor] Commenting on an open window.")

        def builder():
            return worker.run(user_text=prompt)

        self.orchestrator.add(Category.MONITOR, builder)