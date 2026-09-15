"""
energy_monitor.py

Every `interval`, while energy is low, nudges the system volume (and,
best-effort, monitor brightness) down slightly — a passive reflection
of Venus's "tiredness" on the environment.

Does NOT restore the values automatically — deliberate: the natural
response is for the user to adjust it back manually.

The volume/brightness reduction is a side effect on the OS, not a
Gemini call, so it still runs immediately on this thread. Only the
spoken comment goes through the Orchestrator/GeminiWorker pipeline.

Note: the old version of this file had a bug — the line that actually
fired the reaction was mistakenly indented one level too deep, placing
it after a `return` inside the cooldown check, so it was dead code and
never ran. That's fixed here (and made moot regardless, since the
per-monitor cooldown gate this used to sit behind no longer exists —
Orchestrator handles that now).
"""

from ai.MoodController import mood
from ai.GeminiWorker import worker
from Orchestrator import Category
from Monitors.BaseMonitor import BaseMonitor


class EnergyMonitor(BaseMonitor):

    def __init__(
        self,
        orchestrator,
        interval=5000,               # 60 minutes
        volume_reduction=0.05,       # fraction (0.05 = 5%)
        brightness_reduction=7,      # percentage points
        volume_reduction_cap=0.20,   # max accumulated per session
        brightness_reduction_cap=20,
        energy_threshold=30,
    ):
        super().__init__(orchestrator, interval)
        self.volume_reduction = volume_reduction
        self.brightness_reduction = brightness_reduction
        self.volume_reduction_cap = volume_reduction_cap
        self.brightness_reduction_cap = brightness_reduction_cap
        self.energy_threshold = energy_threshold

        self._total_volume_reduced = 0.0
        self._total_brightness_reduced = 0

    def check(self):
        if mood.energy >= self.energy_threshold:
            return

        self._fire()

    def _fire(self):
        print(f"[EnergyMonitor] Energy at {mood.energy}, reducing volume and brightness.")

        self._reduce_volume()
        self._reduce_brightness()

        def builder():
            return worker.run(
                user_text=f"[SYSTEM MESSAGE: Venus energy {mood.energy}/100. Venus is reducing pc volume and brightness.]"
            )

        self.orchestrator.add(Category.MONITOR, builder)

    def _reduce_volume(self):
        if self._total_volume_reduced >= self.volume_reduction_cap:
            print("[EnergyMonitor] Session volume reduction cap already reached. Ignoring.")
            return

        try:
            from pycaw.pycaw import AudioUtilities

            speakers = AudioUtilities.GetSpeakers()
            volume = speakers.EndpointVolume

            current = volume.GetMasterVolumeLevelScalar()

            remaining_room = self.volume_reduction_cap - self._total_volume_reduced
            applicable_reduction = min(self.volume_reduction, remaining_room)

            new_value = max(0.0, current - applicable_reduction)
            volume.SetMasterVolumeLevelScalar(new_value, None)

            self._total_volume_reduced += applicable_reduction

            print(f"[EnergyMonitor] Volume reduced from {current * 100:.0f}% to {new_value * 100:.0f}% "
                  f"(total reduced this session: {self._total_volume_reduced * 100:.0f}%).")

        except Exception as e:
            print(f"[EnergyMonitor] Failed to reduce volume: {e}")

    def _reduce_brightness(self):
        if self._total_brightness_reduced >= self.brightness_reduction_cap:
            print("[EnergyMonitor] Session brightness reduction cap already reached. Ignoring.")
            return

        try:
            from monitorcontrol import get_monitors

            remaining_room = self.brightness_reduction_cap - self._total_brightness_reduced
            applicable_reduction = min(self.brightness_reduction, remaining_room)

            for monitor in get_monitors():
                try:
                    with monitor:
                        current = monitor.get_luminance()
                        new_value = max(0, current - applicable_reduction)
                        monitor.set_luminance(new_value)

                        print(f"[EnergyMonitor] Brightness reduced from {current}% to {new_value}%.")

                except Exception as e:
                    print(f"[EnergyMonitor] Failed to reduce brightness on a monitor (DDC/CI may not be supported): {e}")

            self._total_brightness_reduced += applicable_reduction

        except Exception as e:
            print(f"[EnergyMonitor] Failed to access monitors via DDC/CI: {e}")