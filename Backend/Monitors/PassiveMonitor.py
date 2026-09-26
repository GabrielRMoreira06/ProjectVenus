"""
passive_monitor.py

Owns every passive monitor and starts/stops them together. Each
monitor decides on its own when its condition is met and talks
directly to Orchestrator (see base_monitor.py) — this class doesn't
gate or throttle anything itself. Orchestrator's priority queue and
global cooldown (min_delivery_spacing) already cover that, for every
monitor at once, in one place, instead of each monitor checking a
shared gate before firing.

Each default monitor is built with its enabled/interval pulled from
Preferences (preferences.json) rather than the class's own hardcoded
default, and registered under a stable string id (see
Preferences.MONITOR_CATALOG) so _on_preference_changed can find the
right running instance later when the Preferences tab flips a
checkbox or drags a slider — no restart needed, see BaseMonitor.

Anger is no longer a polling monitor here — MoodController now fires
its DEADPIXEL interaction directly off a threshold check inside
adjust() (see ai/MoodController.py).

To add a new passive monitor: subclass BaseMonitor in Monitors/, add
it to Preferences.MONITOR_CATALOG with a description and default
interval, then add it to _default_monitors() below.
"""


from Monitors.GenericInteraction import GenericInteractionMonitor
from Monitors.HadwereMonitor import HardwareMonitor
from Monitors.ProcessMonitor import ProcessMonitor
from Monitors.ScreenPeakMonitor import ScreenPeekMonitor
from Monitors.UptimeMonitor import UptimeMonitor
from Monitors.EmailMonitor import EmailMonitor
from Preferences import preferences


class PassiveMonitor:

    def __init__(self, orchestrator, monitors=None):
        self.orchestrator = orchestrator
        self._monitors_by_id = {}
        self.monitors = monitors if monitors is not None else self._default_monitors()

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
            interval=preferences.get_monitor_interval(monitor_id),
        )
        monitor.enabled = preferences.is_monitor_enabled(monitor_id)

        self._monitors_by_id[monitor_id] = monitor
        return monitor

    def _on_preference_changed(self, kind, item_id):
        if kind != "monitor":
            return

        monitor = self._monitors_by_id.get(item_id)
        if monitor is None:
            return

        monitor.enabled = preferences.is_monitor_enabled(item_id)
        monitor.interval = preferences.get_monitor_interval(item_id)

    def start(self):
        for monitor in self.monitors:
            monitor.start()

    def stop(self):
        for monitor in self.monitors:
            monitor.stop()