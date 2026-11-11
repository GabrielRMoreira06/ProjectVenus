"""
passive_monitor.py

Owns every passive monitor and the ONE global scheduler that decides
when they run.

Global idle cooldown: every message in the chat (either side) resets a
timer. Each time that timer reaches IDLE_COOLDOWN_SECONDS with no
message in between, one "cooldown" has elapsed and at most ONE monitor
is fired. Monitors never fire in the middle of a conversation.

Pace: each monitor has a `pace` (see Preferences.MONITOR_CATALOG), the
number of elapsed cooldowns between its turns. A monitor whose pace is
reached is put in a FIFO `due` queue. Each cooldown pops from that
queue until one monitor actually fires (check() returned True), so if
two monitors coincide (e.g. pace 3 and 9) the second simply waits for
the next trigger. A monitor's counter restarts the moment it becomes
due, which keeps its cadence even if it waits in the queue.

Cooldown counts are NOT reset by messages — only the idle timer is.
Otherwise a monitor with a high pace would never fire for someone who
chats now and then.

Monitors gated by XP progression (see ai/EXPManager.UNLOCKS) start
with `locked=True`. unlock_monitor() clears the lock and puts the
monitor in the due queue, so it fires on the next idle trigger.

To add a new passive monitor: subclass BaseMonitor in Monitors/, add
it to Preferences.MONITOR_CATALOG with a description and default
pace, then add it to _default_monitors() below.
"""

import threading
import time
import traceback
from collections import deque

from ai.ChatHistory import chat_history
from ai.EXPManager import exp_manager
from Monitors.GenericInteraction import GenericInteractionMonitor
from Monitors.HadwereMonitor import HardwareMonitor
from Monitors.ProcessMonitor import ProcessMonitor
from Monitors.ScreenPeakMonitor import ScreenPeekMonitor
from Monitors.UptimeMonitor import UptimeMonitor
from Monitors.EmailMonitor import EmailMonitor
from Preferences import preferences, IDLE_COOLDOWN_SECONDS

POLL_INTERVAL = 5  # seconds between idle-timer checks


class PassiveMonitor:

    def __init__(self, orchestrator, monitors=None, cooldown=IDLE_COOLDOWN_SECONDS):
        self.orchestrator = orchestrator
        self.cooldown = cooldown

        self._lock = threading.Lock()
        self._last_activity = time.time()
        self._waited = {}   # monitor_id -> cooldowns elapsed since its last turn
        self._due = deque() # monitor_ids waiting for a turn, FIFO
        self._running = False

        self._monitors_by_id = {}
        self.monitors = monitors if monitors is not None else self._default_monitors()

        chat_history.subscribe(self._on_message)
        preferences.subscribe(self._on_preference_changed)

    def _default_monitors(self):
        return [
            self._build("hardware", HardwareMonitor),
            self._build("uptime", UptimeMonitor),
            self._build("process", ProcessMonitor),
            self._build("screenpeek", ScreenPeekMonitor),
            self._build("generic_interaction", GenericInteractionMonitor),
            self._build("email", EmailMonitor),
        ]

    def _build(self, monitor_id, monitor_class):
        monitor = monitor_class(
            self.orchestrator,
            pace=preferences.get_monitor_pace(monitor_id),
        )
        monitor.enabled = preferences.is_monitor_enabled(monitor_id)
        monitor.locked = not exp_manager.is_unlocked("monitor", monitor_id)

        self._monitors_by_id[monitor_id] = monitor
        return monitor

    # ------------------------------------------------------------------
    # Idle tracking
    # ------------------------------------------------------------------

    def _on_message(self, message):
        with self._lock:
            self._last_activity = time.time()

    def _on_preference_changed(self, kind, item_id):
        if kind != "monitor":
            return

        monitor = self._monitors_by_id.get(item_id)
        if monitor is None:
            return

        monitor.enabled = preferences.is_monitor_enabled(item_id)
        monitor.pace = preferences.get_monitor_pace(item_id)

    def unlock_monitor(self, monitor_id):
        monitor = self._monitors_by_id.get(monitor_id)
        if monitor is None:
            return

        monitor.locked = False
        print(f"[PassiveMonitor] '{monitor_id}' unlocked.")

        if monitor.enabled:
            with self._lock:
                if monitor_id not in self._due:
                    self._due.append(monitor_id)

    # ------------------------------------------------------------------
    # Scheduler
    # ------------------------------------------------------------------

    def start(self):
        self._running = True
        threading.Thread(target=self._loop, daemon=True, name="PassiveMonitor").start()

    def stop(self):
        self._running = False

    def _loop(self):
        while self._running:
            time.sleep(POLL_INTERVAL)

            with self._lock:
                idle_for = time.time() - self._last_activity
                if idle_for < self.cooldown:
                    continue

                # Next cooldown starts counting from now.
                self._last_activity = time.time()

            try:
                self._on_cooldown_elapsed()
            except Exception:
                traceback.print_exc()

    def _on_cooldown_elapsed(self):
        with self._lock:
            for monitor_id, monitor in self._monitors_by_id.items():
                if not monitor.enabled or monitor.locked:
                    continue

                if monitor_id in self._due:
                    continue

                self._waited[monitor_id] = self._waited.get(monitor_id, 0) + 1

                if self._waited[monitor_id] >= monitor.pace:
                    self._waited[monitor_id] = 0
                    self._due.append(monitor_id)

        self._fire_next_due()

    def _fire_next_due(self):
        while True:
            with self._lock:
                if not self._due:
                    return
                monitor_id = self._due.popleft()
                monitor = self._monitors_by_id.get(monitor_id)

            if monitor is None or not monitor.enabled or monitor.locked:
                continue

            try:
                fired = monitor.check()
            except Exception:
                traceback.print_exc()
                continue

            if fired:
                print(f"[PassiveMonitor] '{monitor_id}' fired.")
                return