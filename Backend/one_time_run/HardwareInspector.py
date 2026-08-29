"""
hardware_inspector.py

`check()` returns a PROMPT (string) describing what was found, or None
if there's nothing to report — it never calls Gemini directly. It's
OneTimeManager that wraps this prompt and submits it to Orchestrator.
"""

import json
import platform
from pathlib import Path
import psutil
import wmi


class HardwareInspect:

    def __init__(self, state_file="hardware_state.json"):
        # The WMI connection is NOT created here — __init__ runs on the
        # main thread (import time), but check() is called later, from
        # inside OneTimeManager's own thread. COM/WMI objects aren't
        # safe to use across a thread other than the one that created
        # them, so the connection is created lazily, on first use.
        self.state_file = Path(state_file)
        self._wmi = None

    def _get_wmi(self):
        if self._wmi is not None:
            return self._wmi

        try:
            self._wmi = wmi.WMI()
        except Exception as e:
            print(f"[HardwareInspect] Failed to initialize WMI: {e}")
            self._wmi = None

        return self._wmi

    def _collect_specs(self):
        return {
            "cpu": self._collect_cpu(),
            "gpu": self._collect_gpu(),
            "ram_gb": round(psutil.virtual_memory().total / (1024 ** 3)),
            "disk_gb": self._collect_total_disk(),
            "operating_system": self._collect_operating_system(),
        }

    def _collect_cpu(self):
        connection = self._get_wmi()

        if connection is not None:
            try:
                processors = connection.Win32_Processor()
                if processors:
                    return processors[0].Name.strip()
            except Exception as e:
                print(f"[HardwareInspect] Failed to read CPU via WMI: {e}")

        return platform.processor() or "Unknown CPU"

    def _collect_gpu(self):
        connection = self._get_wmi()

        if connection is None:
            return "Unknown GPU"

        try:
            gpus = connection.Win32_VideoController()
            if gpus:
                return gpus[0].Name.strip()
        except Exception as e:
            print(f"[HardwareInspect] Failed to read GPU via WMI: {e}")

        return "Unknown GPU"

    def _collect_total_disk(self):
        connection = self._get_wmi()

        if connection is not None:
            try:
                disks = connection.Win32_DiskDrive()
                if disks:
                    total_bytes = sum(int(d.Size) for d in disks if d.Size)
                    if total_bytes:
                        return round(total_bytes / (1024 ** 3))
            except Exception as e:
                print(f"[HardwareInspect] Failed to read disk via WMI: {e}")

        try:
            usage = psutil.disk_usage("C:\\")
            return round(usage.total / (1024 ** 3))
        except Exception:
            return None

    def _collect_operating_system(self):
        return f"{platform.system()} {platform.release()}"

    def _load_state(self):
        if not self.state_file.exists():
            return None

        try:
            with open(self.state_file, "r", encoding="utf-8") as f:
                content = f.read().strip()
                return json.loads(content) if content else None
        except (json.JSONDecodeError, OSError):
            return None

    def _save_state(self, specs):
        with open(self.state_file, "w", encoding="utf-8") as f:
            json.dump(specs, f, ensure_ascii=False, indent=4)

    def _format_specs(self, specs):
        parts = [
            f"CPU: {specs.get('cpu')}",
            f"GPU: {specs.get('gpu')}",
            f"RAM: {specs.get('ram_gb')}GB",
            f"Disk: {specs.get('disk_gb')}GB",
            f"OS: {specs.get('operating_system')}",
        ]
        return "; ".join(parts)

    def check(self):
        current_specs = self._collect_specs()
        previous_specs = self._load_state()

        self._save_state(current_specs)

        if previous_specs is None:
            summary = self._format_specs(current_specs)
            print(f"[HardwareInspect] First hardware check: {summary}")

            return f"[SYSTEM MESSAGE: you checked the pc specs you're living in: {summary}]"

        changes = []

        for key, label in (
            ("cpu", "CPU"),
            ("gpu", "GPU"),
            ("ram_gb", "RAM"),
            ("disk_gb", "Disk"),
            ("operating_system", "OS"),
        ):
            old_value = previous_specs.get(key)
            new_value = current_specs.get(key)

            if old_value is not None and old_value != new_value:
                changes.append(f"{label}: '{old_value}' -> '{new_value}'")

        if not changes:
            return None

        summary = "; ".join(changes)
        print(f"[HardwareInspect] Hardware change detected: {summary}")

        return f"[SYSTEM MESSAGE: User updated their hardware. Changes: {summary}.]"