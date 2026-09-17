"""
base_monitor.py

Base class for passive monitors. Each monitor runs on its own thread,
checking its condition on a fixed interval — that interval IS the
monitor's internal cooldown: what stops THIS monitor from firing more
often than makes sense for whatever it's watching.

Global cooldown and priority ordering ACROSS different monitors is not
this class's job — that's handled entirely by Orchestrator once a
monitor calls orchestrator.add(). A monitor only ever has to decide
"is my own condition met right now?", never "am I allowed to run given
everything else going on."

Subclasses implement `check()`, which should decide whether its
condition is met and, if so, build a zero-argument builder function
and call `self.orchestrator.add(category, builder)`.

`interval` and `enabled` are both read fresh on every loop iteration,
not just once at construction — this is what lets PassiveMonitor apply
a Preferences change (checkbox/slider in the panel) live, just by
setting these two attributes, with no thread restart needed.
"""

import threading
import time


class BaseMonitor:

    def __init__(self, orchestrator, interval):
        self.orchestrator = orchestrator
        self.interval = interval
        # Controlled by Preferences via PassiveMonitor — defaults to
        # True so a monitor built without going through
        # PassiveMonitor._build() (e.g. in a quick test script) still
        # runs normally.
        self.enabled = True
        self._running = False

    def start(self):
        self._running = True
        threading.Thread(target=self._loop, daemon=True, name=self.__class__.__name__).start()

    def stop(self):
        self._running = False

    def _loop(self):
        while self._running:
            time.sleep(self.interval)
            if self.enabled:
                self.check()

    def check(self):
        raise NotImplementedError