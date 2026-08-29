"""
disk_inspect.py

"Once per session" disk check, run through OneTimeManager, same
pattern as HardwareInspect. Unlike a continuous monitor with
per-partition rearming, this is a single snapshot: partitions that are
full at check time are reported once — there's no "again" within a
check that only ever runs once per session.

`check()` follows the same contract as HardwareInspect: returns a
PROMPT (string) or None — never calls Gemini directly.
"""

import psutil


class DiskInspect:

    def __init__(self, usage_limit=85):
        self.usage_limit = usage_limit

    def _collect_usage(self):
        usage_by_partition = {}

        for partition in psutil.disk_partitions(all=False):
            if "cdrom" in partition.opts or partition.fstype == "":
                continue

            try:
                usage = psutil.disk_usage(partition.mountpoint)
                usage_by_partition[partition.mountpoint] = usage.percent
            except (PermissionError, OSError):
                continue

        return usage_by_partition

    def check(self):
        usage_by_partition = self._collect_usage()

        full_partitions = {
            partition: usage
            for partition, usage in usage_by_partition.items()
            if usage >= self.usage_limit
        }

        if not full_partitions:
            return None

        summary = "; ".join(
            f"{partition} at {usage:.0f}%" for partition, usage in full_partitions.items()
        )

        print(f"[DiskInspect] Partitions above the limit: {summary}")

        return f"[SYSTEM MESSAGE: You checked the disk and noticed these drives are low on space: {summary}.]"