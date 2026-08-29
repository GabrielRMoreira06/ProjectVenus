"""
memory_cleanup_check.py

Periodic maintenance check: removes expired memory entries. Always
returns None — this never produces a Venus response, it's just
housekeeping riding on the same "once per session" scheduling as the
other checks.

Takes a `memory_manager` explicitly rather than constructing its own —
GeminiWorker already owns a MemoryManager instance (`worker.memory`),
and reusing that SAME instance avoids two separate in-memory copies of
memory.json quietly drifting out of sync with each other.
"""


class MemoryCleanupCheck:

    def __init__(self, memory_manager):
        self.memory = memory_manager

    def check(self):
        self.memory.clear_expired()
        return None