"""
gemini_worker.py

Wraps a single, ongoing Gemini chat session and turns raw model output
into a structured Venus response (text + action + mood shift + memory
operation).

Design notes:
  - GeminiWorker is a class, not a module of bare functions with
    module-level globals. The chat session and the request counter
    live on the instance — create one and reuse it (see `worker` at
    the bottom) instead of importing loose functions.
  - mood_controller and memory_manager are constructor parameters
    (defaulting to the shared instances) rather than hardcoded
    imports, so this class doesn't lock itself to one specific
    implementation of either.
"""

from datetime import datetime

from dotenv import load_dotenv
from google import genai
from google.genai import types

from config import GEMINI_KEY
from ai.Prompts import SYSTEM_INSTRUCTIONS, RESPONSE_RULES
from ai.ResponseParser import ResponseParser
from ai.MoodController import mood
from ai.MemoryManager import MemoryManager
from ai.TTSWorker import tts_worker as shared_tts_worker
from ai.ImageSearch import search_image as default_image_search


load_dotenv()

MODEL_NAME = "gemini-3.1-flash-lite"

# How often (in requests) the full memory block is resent to the model.
# The chat session already keeps prior turns in its own history, so
# resending every request would be redundant — this just guards
# against memory silently drifting out of context on very long
# sessions.
MEMORY_RESEND_INTERVAL = 10


class GeminiWorker:

    def __init__(self, mood_controller=None, memory_manager=None, tts_worker=None,
                 image_search=None, model_name=MODEL_NAME):
        self.client = genai.Client(api_key=GEMINI_KEY)
        self.mood = mood_controller or mood
        self.memory = memory_manager or MemoryManager()
        self.tts = tts_worker or shared_tts_worker
        self.search_image = image_search or default_image_search
        self.parser = ResponseParser()

        self.chat = self.client.chats.create(
            model=model_name,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_INSTRUCTIONS,
                temperature=0.8,
            ),
        )

        self._request_count = 0

    def run(self, user_text=None, image=None):
        """
        Sends one message to the ongoing chat session and returns a
        parsed dict (text/action/image_query/mood_variant/mood_shift/
        memory_type/memory_text/memory_expire/audio_path/image_path).

        Also applies the resulting mood shift, stores any memory the
        model asked to save, generates the spoken audio for the
        response text, and — if ACTION is OPENIMAGE — resolves
        IMAGE_QUERY into an actual local file. This is the one place
        all four side effects happen, so callers never have to
        remember to do them.
        """
        try:
            self._request_count += 1
            include_memory = (self._request_count - 1) % MEMORY_RESEND_INTERVAL == 0

            prompt = self._build_prompt(user_text, include_memory)
            content = [prompt] if image is None else [prompt, image]

            response = self.chat.send_message(content)
            parsed = self.parser.parse(response.text)

            # Silent responses (empty TEXT) have nothing to speak — skip
            # the ElevenLabs call entirely rather than generating audio
            # for silence.
            parsed["audio_path"] = self.tts.generate_audio(parsed["text"]) if parsed["text"] else None

            parsed["image_path"] = self._resolve_image(parsed)

            self.mood.apply_shift(parsed["mood_variant"], parsed["mood_shift"])

            if parsed["memory_type"] != "NONE":
                self.memory.save(parsed["memory_type"], parsed["memory_text"], parsed["memory_expire"])

            return parsed

        except Exception as error:
            print("ERROR IN GeminiWorker.run:", error)
            raise

    def _resolve_image(self, parsed):
        """
        When Gemini's own ACTION is OPENIMAGE, it comes with an
        IMAGE_QUERY but no actual image yet — this is what turns that
        query into a real local file via image_search. If the query is
        missing or the search comes up empty, ACTION falls back to
        NONE (mutating `parsed` directly) rather than shipping an
        OPENIMAGE action with nothing to show for it.
        """
        if parsed["action"] != "OPENIMAGE":
            return None

        query = parsed["image_query"]

        if not query or query == "NONE":
            parsed["action"] = "NONE"
            return None

        image_path = self.search_image(query)

        if image_path is None:
            parsed["action"] = "NONE"

        return image_path

    def _build_prompt(self, user_text, include_memory):
        sections = [
            f"TIME: {datetime.now().strftime('%H:%M')}",
            f"=== VENUS MOOD ===\n{self.mood.get_prompt()}",
            f"=== RESPONSE RULES ===\n{RESPONSE_RULES}",

        ]

        if include_memory:
            sections.append(f"=== VENUS MEMORY ===\n{self.memory.get_prompt()}")
            print(f"[GeminiWorker] Request #{self._request_count} — including memory block.")

        if user_text:
            sections.append(f"=== USER INPUT ===\n{user_text}")

        return "\n\n".join(sections)


# Shared instance used by the rest of the backend — same pattern as
# `mood` in mood_controller.py. There's only one Venus per process.
worker = GeminiWorker()