"""
process_monitor.py

Watches whether any single process is consuming CPU or RAM above the
limit. Rearms when the process drops below the limit (or closes).

CPU is normalized by core count, so cpu_limit=50 means "50% of TOTAL
system capacity", not 50% of a single core — psutil.Process.cpu_percent()
is per-core by default and can exceed 100% on multi-core CPUs.

System Idle Process and System are always ignored: not real user
processes, and not meaningful in this context.

Per-process CPU% is measured "since the last check", so the
psutil.Process objects are kept between checks instead of being
re-queried from scratch every time.
"""

import psutil

from ai.GeminiWorker import worker
from Orchestrator import Category
from Monitors.BaseMonitor import BaseMonitor

IGNORED_SYSTEM_PIDS = {0, 4}  # 0 = System Idle Process, 4 = System


class ProcessMonitor(BaseMonitor):

    def __init__(self, orchestrator, interval=3600, cpu_limit=85, ram_limit=85):
        super().__init__(orchestrator, interval)
        self.cpu_limit = cpu_limit
        self.ram_limit = ram_limit

        self._core_count = psutil.cpu_count() or 1

        self._tracked_processes = {}  # pid -> psutil.Process
        self._already_alerted = {}    # pid -> bool

    def check(self):
        current_pids = set()

        for proc in psutil.process_iter(["pid", "name"]):
            pid = proc.info["pid"]

            if pid in IGNORED_SYSTEM_PIDS:
                continue

            current_pids.add(pid)

            if pid not in self._tracked_processes:
                try:
                    p = psutil.Process(pid)
                    p.cpu_percent(interval=None)  # first call just sets the baseline
                    self._tracked_processes[pid] = p
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue

        # Drop processes that have closed.
        for pid in list(self._tracked_processes.keys()):
            if pid not in current_pids:
                del self._tracked_processes[pid]
                self._already_alerted.pop(pid, None)

        candidate = None  # (pid, name, kind, value)

        for pid, p in self._tracked_processes.items():
            try:
                cpu = p.cpu_percent(interval=None) / self._core_count
                ram = p.memory_percent()
                name = p.name()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

            already_alerted = self._already_alerted.get(pid, False)
            exceeded = cpu >= self.cpu_limit or ram >= self.ram_limit

            if not exceeded:
                self._already_alerted[pid] = False
                continue

            if already_alerted:
                continue

            kind = "CPU" if cpu >= self.cpu_limit else "RAM"
            value = cpu if kind == "CPU" else ram

            candidate = (pid, name, kind, value)
            break

        if candidate is None:
            return

        pid, name, kind, value = candidate
        self._already_alerted[pid] = True
        self._fire(name, kind, value)

    def _fire(self, name, kind, value):
        print(f"[ProcessMonitor] Process '{name}' using {value:.0f}% of {kind}, alerting.")

        def builder():
            return worker.run(
                user_text=f"[SYSTEM MESSAGE: Venus detected the process '{name}' consuming {value:.0f}% of {kind}.]"
            )

        self.orchestrator.add(Category.MONITOR, builder)