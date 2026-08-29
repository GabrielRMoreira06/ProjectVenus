"""
passive_monitor.py

Owns every passive monitor and starts/stops them together. Each
monitor decides on its own when its condition is met and talks
directly to Orchestrator (see base_monitor.py) — this class doesn't
gate or throttle anything itself. Orchestrator's priority queue and
global cooldown (min_delivery_spacing) already cover that, for every
monitor at once, in one place, instead of each monitor checking a
shared gate before firing.

To add a new passive monitor: subclass BaseMonitor in  Monitors/,
then add an instance of it to the list in _default_monitors().
"""

from Monitors.MoodMonitors.AngerMonitor import AngerMonitor
from Monitors.MoodMonitors.BoredomMonitor import BoredomMonitor
from Monitors.MoodMonitors.EnergyMonitor import EnergyMonitor
from Monitors.GenericInteraction import GenericInteractionMonitor
from Monitors.HadwereMonitor import HardwareMonitor
from Monitors.ProcessMonitor import ProcessMonitor
from Monitors.ScreenPeakMonitor import ScreenPeekMonitor
from Monitors.UptimeMonitor import UptimeMonitor


class PassiveMonitor:

    def __init__(self, orchestrator, monitors=None):
        self.orchestrator = orchestrator
        self.monitors = monitors if monitors is not None else self._default_monitors()

    def _default_monitors(self):
        return [
            BoredomMonitor(self.orchestrator),
            HardwareMonitor(self.orchestrator),
            UptimeMonitor(self.orchestrator),
            ProcessMonitor(self.orchestrator),
            AngerMonitor(self.orchestrator),
            EnergyMonitor(self.orchestrator),
            ScreenPeekMonitor(self.orchestrator),
            GenericInteractionMonitor(self.orchestrator),
        ]

    def start(self):
        for monitor in self.monitors:
            monitor.start()

    def stop(self):
        for monitor in self.monitors:
            monitor.stop()