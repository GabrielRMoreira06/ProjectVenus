"""
LowerBrightnessVolume.py

Reduces system volume and monitor brightness a little — Venus's
passive reaction to low energy. NOT registered in ON_CALL_ACTIONS (see
on_call_actions/__init__.py): unlike find_file/clean_disk/etc., this
isn't dispatched through Server.py's on-call-action pipeline, since
it's never the ACTION of a response reaching /response — MoodController
calls .run() directly, synchronously, from inside its own Orchestrator
builder (see MoodController._fire_energy_interaction). Just filed
under on_call_actions/ alongside the others since it's the same kind
of backend-only OS side effect.

Kept as a class with a shared module-level instance (same pattern as
MoodController/TTSWorker/Preferences) because the reduction caps are
cumulative for the whole session, not per-call — moving the two
methods out without keeping that state together would have reset the
caps on every single call.
"""


class LowerBrightnessVolume:

    def __init__(
        self,
        volume_reduction=0.05,
        brightness_reduction=7,
        volume_reduction_cap=0.20,
        brightness_reduction_cap=20,
    ):
        self.volume_reduction = volume_reduction
        self.brightness_reduction = brightness_reduction
        self.volume_reduction_cap = volume_reduction_cap
        self.brightness_reduction_cap = brightness_reduction_cap

        self._total_volume_reduced = 0.0
        self._total_brightness_reduced = 0

    def run(self):
        """Reduces volume and brightness one step, respecting each session cap."""
        self._reduce_volume()
        self._reduce_brightness()

    def _reduce_volume(self):
        if self._total_volume_reduced >= self.volume_reduction_cap:
            print("[LowerBrightnessVolume] Session volume reduction cap already reached. Ignoring.")
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

            print(f"[LowerBrightnessVolume] Volume reduced from {current * 100:.0f}% to {new_value * 100:.0f}% "
                  f"(total reduced this session: {self._total_volume_reduced * 100:.0f}%).")

        except Exception as e:
            print(f"[LowerBrightnessVolume] Failed to reduce volume: {e}")

    def _reduce_brightness(self):
        if self._total_brightness_reduced >= self.brightness_reduction_cap:
            print("[LowerBrightnessVolume] Session brightness reduction cap already reached. Ignoring.")
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

                        print(f"[LowerBrightnessVolume] Brightness reduced from {current}% to {new_value}%.")

                except Exception as e:
                    print(f"[LowerBrightnessVolume] Failed to reduce brightness on a monitor (DDC/CI may not be supported): {e}")

            self._total_brightness_reduced += applicable_reduction

        except Exception as e:
            print(f"[LowerBrightnessVolume] Failed to access monitors via DDC/CI: {e}")


# Shared instance, same pattern as `mood`/`worker`/`tts_worker` elsewhere —
# there's only one session's worth of reduction caps per process.
lower_brightness_volume = LowerBrightnessVolume()