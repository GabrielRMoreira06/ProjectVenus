"""
hardware_monitor.py

Watches overall CPU and RAM usage. When either crosses `usage_limit`,
Venus comments on it.

GPU and temperature are not monitored: they'd require vendor-specific
libraries (GPUtil is NVIDIA-only, AMD would need ADL or an external
app like LibreHardwareMonitor), which isn't wanted here.
"""

import psutil

from ai.GeminiWorker import worker
from Orchestrator import Category
from Monitors.BaseMonitor import BaseMonitor


class HardwareMonitor(BaseMonitor):

    def __init__(self, orchestrator, interval=900, usage_limit=85):
        super().__init__(orchestrator, interval)
        self.usage_limit = usage_limit

    def check(self):
        usage = self._collect_usage()

        for component, value in usage.items():
            if value < self.usage_limit:
                continue

            self._fire(component, value)
            return  # one alert per check is enough

    def _collect_usage(self):
        return {
            "CPU": psutil.cpu_percent(interval=1),
            "RAM": psutil.virtual_memory().percent,
        }

    def _fire(self, component, usage):
        print(f"[HardwareMonitor] {component} usage at {usage:.0f}%, alerting.")

        def builder():
            return worker.run(
                user_text=f"[SYSTEM MESSAGE: Venus detected that {component} usage is {usage:.0f}%.]"
            )

        self.orchestrator.add(Category.MONITOR, builder)