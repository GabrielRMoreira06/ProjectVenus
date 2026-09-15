"""
uptime_monitor.py

Tracks how long the PC has been on (since boot, not since the app
opened). Alerts Venus the first time uptime crosses `initial_threshold`,
then repeats every `repeat_interval` of additional uptime, until the PC
is restarted.

Example: initial_threshold=4h, repeat_interval=2h -> alerts at 4h, 6h,
8h, 10h... The next threshold is recalculated from the real boot time,
so this behaves correctly even if the app itself restarts midway
(never loses or duplicates a rearm).
"""

import time
import psutil

from ai.GeminiWorker import worker
from Orchestrator import Category
from Monitors.BaseMonitor import BaseMonitor


class UptimeMonitor(BaseMonitor):

    def __init__(self, orchestrator, interval=72000, initial_threshold=4 * 3600, repeat_interval=2 * 3600):
        super().__init__(orchestrator, interval)
        self.initial_threshold = initial_threshold
        self.repeat_interval = repeat_interval

        self._current_boot_time = None
        self._next_threshold = initial_threshold

    def _uptime_seconds(self):
        return time.time() - psutil.boot_time()

    def check(self):
        boot_time = psutil.boot_time()

        # Detects a PC restart: if boot_time changed, reset progress.
        if self._current_boot_time != boot_time:
            self._current_boot_time = boot_time
            self._next_threshold = self.initial_threshold

        uptime = self._uptime_seconds()

        if uptime < self._next_threshold:
            return

        self._fire(uptime)

        # Schedules the next alert regardless of anything else — avoids
        # re-alerting seconds later for the same threshold.
        self._next_threshold += self.repeat_interval

    def _fire(self, uptime):
        hours = uptime / 3600
        print(f"[UptimeMonitor] Uptime at {hours:.1f}h, alerting.")

        def builder():
            return worker.run(
                user_text=f"[SYSTEM MESSAGE: you detected the user's PC has been on for over {hours:.0f} hours straight.]"
            )

        self.orchestrator.add(Category.MONITOR, builder)