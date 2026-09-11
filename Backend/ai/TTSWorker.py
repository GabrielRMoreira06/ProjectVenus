"""
TTSWorker.py

Wraps Piper (local, offline neural TTS) to turn Venus's response text
into a WAV file on disk and returns its path.

Swapped in to replace ElevenLabs: Piper runs entirely on-device via
onnxruntime, so there's no per-request API cost and no network call —
it was ElevenLabs' credit consumption that made this worth doing, not
a quality complaint.

Voice model setup (one-time, outside this file):
    pip install piper-tts
    python -m piper.download_voices en_US-lessac-medium
This downloads a <voice>.onnx + <voice>.onnx.json pair. Point
PIPER_MODEL_PATH (config.py) at the .onnx file — the .json config is
expected to sit right next to it, Piper finds it automatically.

skip_synthesis mirrors the old ElevenLabs skip_api flag — True returns
a placeholder file without touching the model at all, useful for
testing the rest of the pipeline without paying the model-load cost.

NOTE: this now returns a .wav file, not .mp3. If the Unity side
hardcodes AudioType.MPEG for UnityWebRequestMultimedia.GetAudioClip
when fetching /audio/<id>, that needs to change to AudioType.WAV, or
Unity will fail to decode the clip.
"""

import tempfile
import wave
from pathlib import Path
import wave
import numpy as np
from scipy import signal
from config import PIPER_MODEL_PATH


class TTSWorker:

    def __init__(self, model_path=PIPER_MODEL_PATH, skip_synthesis=False):
        self.model_path = model_path
        self.skip_synthesis = skip_synthesis
        self._voice = None  # lazy-loaded, see _get_voice()

    def _get_voice(self):
        """
        The PiperVoice is NOT loaded in __init__ — that pulls in
        onnxruntime and reads the model off disk, which is wasted work
        if skip_synthesis is True or generate_audio() never actually
        gets called (e.g. short-lived test scripts).
        """
        if self._voice is not None:
            return self._voice

        from piper import PiperVoice

        if not Path(self.model_path).exists():
            raise FileNotFoundError(
                f"[TTSWorker] Piper voice model not found at '{self.model_path}'. "
                f"Run: python -m piper.download_voices <voice_name>, then point "
                f"PIPER_MODEL_PATH at the resulting .onnx file."
            )

        self._voice = PiperVoice.load(self.model_path)
        return self._voice

    def apply_blowout(self, wav_path, gain=3.0):
        """
        Hard-clips the waveform to produce a harsh, distorted "blown out"
        sound — used for the SCREAM action. Multiplying by `gain` pushes
        the signal well past the int16 range; clipping it back down is
        what produces the flattened, distorted peaks. Mutates the file at
        wav_path in place.

        gain: how hard to push it. ~3-4 is noticeably distorted but still
        intelligible; ~6+ starts turning to harsh noise.
        """
        with wave.open(wav_path, "rb") as wf:
            n_channels = wf.getnchannels()
            sampwidth = wf.getsampwidth()
            framerate = wf.getframerate()
            n_frames = wf.getnframes()
            raw = wf.readframes(n_frames)

        audio = np.frombuffer(raw, dtype=np.int16).astype(np.float32)
        boosted = audio * gain
        clipped = np.clip(boosted, -32768, 32767).astype(np.int16)

        with wave.open(wav_path, "wb") as wf:
            wf.setnchannels(n_channels)
            wf.setsampwidth(sampwidth)
            wf.setframerate(framerate)
            wf.writeframes(clipped.tobytes())


    @staticmethod
    def _apply_robotic_effect(
            wav_path,
            carrier_freq=900,
            carrier_shape="sine",
            mix=0.2,
            bits=20,
            highpass_freq=550,
            lowpass_freq=10000,
            compression=0.2
    ):
        with wave.open(wav_path, "rb") as wf:
            channels = wf.getnchannels()
            sample_width = wf.getsampwidth()
            sample_rate = wf.getframerate()
            frames = wf.getnframes()
            raw = wf.readframes(frames)

        if sample_width != 2:
            raise ValueError("Only 16-bit PCM WAV files are supported.")

        audio = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0

        if channels == 1:
            audio = audio.reshape(1, -1)
        else:
            audio = audio.reshape(-1, channels).T

        length = audio.shape[1]

        if carrier_freq > 0 and mix > 0:
            mix = max(0.0, min(1.0, mix))
            t = np.arange(length) / sample_rate

            if carrier_shape == "square":
                carrier = np.sign(np.sin(2 * np.pi * carrier_freq * t))
            else:
                carrier = np.sin(2 * np.pi * carrier_freq * t)

            for ch in range(channels):
                modulated = audio[ch] * carrier
                audio[ch] = audio[ch] * (1 - mix) + modulated * mix

        if bits is not None:
            bits = max(6, min(16, int(bits)))
            levels = 2 ** bits
            audio = np.round(audio * levels) / levels

        if highpass_freq > 0:
            cutoff = min(highpass_freq, sample_rate * 0.45)
            sos = signal.butter(3, cutoff, btype="highpass", fs=sample_rate, output="sos")
            for ch in range(channels):
                audio[ch] = signal.sosfilt(sos, audio[ch])

        if lowpass_freq > 0:
            cutoff = min(lowpass_freq, sample_rate * 0.45)
            sos = signal.butter(3, cutoff, btype="lowpass", fs=sample_rate, output="sos")
            for ch in range(channels):
                audio[ch] = signal.sosfilt(sos, audio[ch])

        if compression > 0:
            compression = max(0.0, min(1.0, compression))
            threshold = 0.35
            ratio = 1 + compression * 6
            magnitude = np.abs(audio)
            compressed = np.where(
                magnitude > threshold,
                threshold + (magnitude - threshold) / ratio,
                magnitude
            )
            audio = np.sign(audio) * compressed

        peak = np.max(np.abs(audio))
        if peak > 0.98:
            audio *= 0.98 / peak

        audio = np.clip(audio, -1.0, 1.0)

        if channels == 1:
            output = audio[0]
        else:
            output = audio.T.flatten()

        output = (output * 32767).astype(np.int16)

        with wave.open(wav_path, "wb") as wf:
            wf.setnchannels(channels)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)
            wf.writeframes(output.tobytes())

    def generate_audio(self, text):
        """
        Returns the path to a WAV file with `text` spoken in Venus's
        voice. While skip_synthesis is True, returns a placeholder file
        instead of running the model at all.
        """
        if self.skip_synthesis:
            return r"C:\Users\User\Documents\ProjectVenus\Backend\audio.wav"

        try:
            voice = self._get_voice()

            output_file = tempfile.NamedTemporaryFile(delete=False, suffix=".wav")
            output_file.close()

            with wave.open(output_file.name, "wb") as wav_file:
                voice.synthesize_wav(text, wav_file)

            self._apply_robotic_effect(output_file.name)

            return output_file.name

        except Exception:
            import traceback
            traceback.print_exc()
            raise


# Shared instance, same pattern as `mood` and `worker` elsewhere —
# there's only one Venus voice per process.
tts_worker = TTSWorker()