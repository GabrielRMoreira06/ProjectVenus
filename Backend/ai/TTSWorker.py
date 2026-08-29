"""
tts_worker.py

Wraps ElevenLabs text-to-speech: turns Venus's response text into an
MP3 file on disk and returns its path.

skip_api defaults to True on purpose — testing the rest of the
pipeline (Orchestrator, GeminiWorker, monitors, ...) doesn't need to
burn ElevenLabs credits on every run. Flip it per-instance when audio
actually needs testing, instead of editing this file back and forth.
"""

import tempfile

from dotenv import load_dotenv
from elevenlabs.client import ElevenLabs

from config import ELEVEN_KEY, VOICE_ID

load_dotenv()


class TTSWorker:

    def __init__(self, voice_id=VOICE_ID, model_id="eleven_v3", skip_api=True):
        self.client = ElevenLabs(api_key=ELEVEN_KEY)
        self.voice_id = voice_id
        self.model_id = model_id
        self.skip_api = skip_api

    def generate_audio(self, text):
        """
        Returns the path to an MP3 file with `text` spoken in Venus's
        voice. While skip_api is True, returns a placeholder file
        instead of calling ElevenLabs at all.
        """
        if self.skip_api:
            return r"C:\Users\User\Documents\ProjectVenus\Backend\audio.mp3"
        try:
            audio = self.client.text_to_speech.convert(
                text=text,
                voice_id=self.voice_id,
                model_id=self.model_id,
                output_format="mp3_44100_128",
            )

            output_file = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3")

            for chunk in audio:
                output_file.write(chunk)
            output_file.close()

            return output_file.name

        except Exception:
            import traceback
            traceback.print_exc()
            raise


# Shared instance, same pattern as `mood` and `worker` elsewhere —
# there's only one Venus voice per process.
tts_worker = TTSWorker()