"""
base_monitor.py

Base class for passive monitors. A monitor no longer has its own
thread or its own timer: PassiveMonitor owns the single global idle
cooldown and decides when each monitor gets a turn.

`pace` is how many global idle cooldowns must pass between this
monitor's turns (pace 3 = every 3rd cooldown). `enabled`, `locked` and
`pace` are read fresh by PassiveMonitor, so Preferences changes and XP
unlocks apply live. `locked` is the XP-progression gate (see
ai/EXPManager.py): a locked monitor never gets a turn, regardless of
`enabled`.

Subclasses implement `check()`. It returns True if it actually queued
something with `self.orchestrator.add(category, builder)`, and False
if its condition wasn't met — in that case PassiveMonitor immediately
gives the turn to the next due monitor instead of wasting the slot.
"""


class BaseMonitor:

    def __init__(self, orchestrator, pace=1):
        self.orchestrator = orchestrator
        self.pace = pace
        self.enabled = True
        self.locked = False

    def check(self):
        raise NotImplementedError