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
  - The memory block is no longer resent on a fixed request-count
    interval. It's sent only when the caller explicitly asks for it
    via include_memory=True — currently: once per boot greeting, and
    once per GenericInteractionMonitor firing. Regular user messages
    never carry the memory block.
  - The RESPONSE RULES / RESPONSE RULES EXPLANATION sent to Gemini are
    built from the action ids permitted for THIS call — see
    allowed_actions below. A normal call shows the full regular
    catalog (Preferences only decides whether a *pick* gets denied
    after the fact, see the ACTION check below); a restricted call
    (e.g. a mood threshold offering only one escalation action) shows
    just that narrower ACTION line instead.
"""

from datetime import datetime
import time
from dotenv import load_dotenv
from google import genai
from google.genai import types
from config import GEMINI_KEY
from Preferences import preferences
from Orchestrator import Category
from ai.Prompts import (
    SYSTEM_INSTRUCTIONS,
    ACTIONS,
    build_response_rules,
    build_response_rules_explanation,
)
from ai.ResponseParser import ResponseParser
from ai.MoodController import mood
from ai.MemoryManager import MemoryManager
from ai.TTSWorker import tts_worker as shared_tts_worker
from ai.ImageSearch import search_image as default_image_search


load_dotenv()

MODEL_NAME = "gemini-3.5-flash-lite"

# How often (in requests) the response rules explanation is resent.
RESPONSE_RULES_EXPLANATION_INTERVAL = 5

# Retry configuration for temporary Gemini 503 errors.
MAX_RETRIES = 3
RETRY_DELAY = 2


class GeminiWorker:

    def __init__(
        self,
        mood_controller=None,
        memory_manager=None,
        tts_worker=None,
        image_search=None,
        model_name=MODEL_NAME
    ):
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
            ),
        )

        self._request_count = 0

    def run(self, user_text=None, image=None, include_memory=False, allowed_actions=None):
        """
        Sends one message to the ongoing chat session and returns a
        parsed dict (text/action/image_query/mood_variant/mood_shift/
        memory_type/memory_text/memory_expire/audio_path/image_path).

        allowed_actions: which ACTIONs are offered/permitted for THIS
        call. None (default) = a normal turn — prompt shows the full
        regular catalog (ai/Prompts.ACTIONS), and a pick is denied
        after the fact if the user disabled it in Preferences. Pass an
        explicit set/list to restrict the prompt itself to just those
        actions (plus the always-implicit NONE) — used for narrow,
        call-scoped offers like a mood threshold that should only ever
        offer one specific action.

        include_memory: whether to include the full VENUS MEMORY block
        in this prompt. Callers opt in explicitly — currently only the
        boot greeting and GenericInteractionMonitor do this. Everything
        else (normal user turns) omits it.

        Also applies the resulting mood shift, stores any memory the
        model asked to save, generates the spoken audio for the
        response text, and — if ACTION is SHOWIMAGE — resolves
        IMAGE_QUERY into an actual local file.
        """
        try:
            self._request_count += 1

            include_rules_explanation = (
                self._request_count % RESPONSE_RULES_EXPLANATION_INTERVAL == 0
            )

            prompt = self._build_prompt(
                user_text,
                include_memory,
                include_rules_explanation,
                allowed_actions,
            )

            content = [prompt] if image is None else [prompt, image]

            # Automatic retry for temporary 503 errors.
            response = None

            for attempt in range(MAX_RETRIES):
                try:
                    response = self.chat.send_message(content)
                    break

                except Exception as error:
                    error_text = str(error)

                    # Only retry on 503 / service-unavailable errors.
                    if "503" not in error_text and "UNAVAILABLE" not in error_text:
                        raise

                    if attempt == MAX_RETRIES - 1:
                        raise

                    delay = RETRY_DELAY * (2 ** attempt)

                    print(
                        f"[GeminiWorker] Gemini 503. "
                        f"Retry {attempt + 1}/{MAX_RETRIES - 1} "
                        f"in {delay}s..."
                    )

                    time.sleep(delay)

            parsed = self.parser.parse(response.text)

            permitted_actions = (
                set(allowed_actions) if allowed_actions is not None else preferences.enabled_actions()
            )

            if parsed["action"] != "NONE" and parsed["action"] not in permitted_actions:
                denied_action = parsed["action"]
                parsed["action"] = "NONE"
                self._deny_action(denied_action)

            # Silent responses (empty TEXT) have nothing to speak.
            parsed["audio_path"] = (
                self.tts.generate_audio(parsed["text"])
                if parsed["text"]
                else None
            )

            if parsed["action"] == "SCREAM" and parsed["audio_path"]:
                self.tts.apply_blowout(parsed["audio_path"])

            parsed["image_path"] = self._resolve_image(parsed)

            self.mood.apply_shift(
                parsed["mood_variant"],
                parsed["mood_shift"]
            )

            if parsed["memory_type"] == "EDIT":
                self.memory.edit(
                    parsed["memory_id"],
                    parsed["memory_text"],
                    parsed["memory_expire"]
                )
            elif parsed["memory_type"] != "NONE":
                self.memory.save(
                    parsed["memory_type"],
                    parsed["memory_text"],
                    parsed["memory_expire"]
                )

            return parsed

        except Exception as error:
            print("ERROR IN GeminiWorker.run:", error)
            raise

    def _deny_action(self, action):
        """
        Tells Gemini, as a follow-up SYSTEM message, that the action it
        just picked was denied — instead of silently dropping it.
        `orchestrator` is looked up lazily via sys.modules["__main__"],
        same reason as Reminder.py/EXPManager.py: Server.py constructs
        it after this module is imported.
        """
        print(f"[GeminiWorker] Action '{action}' denied for this request.")

        import sys
        orchestrator = sys.modules["__main__"].orchestrator

        def builder():
            return self.run(user_text=f"[SYSTEM MESSAGE: you tried to use {action} but it was denied.]")

        orchestrator.add(Category.SYSTEM, builder)

    def _resolve_image(self, parsed):
        """
        When Gemini's own ACTION is SHOWIMAGE, it comes with an
        IMAGE_QUERY but no actual image yet — this is what turns that
        query into a real local file via image_search.
        """
        if parsed["action"] != "SHOWIMAGE":
            return None

        query = parsed["image_query"]

        if not query or query == "NONE":
            parsed["action"] = "NONE"
            return None

        image_path = self.search_image(query)

        if image_path is None:
            parsed["action"] = "NONE"

        return image_path

    def _build_prompt(
        self,
        user_text,
        include_memory,
        include_rules_explanation,
        allowed_actions=None,
    ):
        action_ids = list(ACTIONS.keys()) if allowed_actions is None else list(allowed_actions)

        sections = [
            f"TIME: {datetime.now().strftime('%H:%M')}",
            f"=== VENUS MOOD ===\n{self.mood.get_prompt()}",
            f"=== RESPONSE RULES ===\n{build_response_rules(action_ids)}",
        ]

        if include_rules_explanation:
            sections.append(
                f"=== RESPONSE RULES EXPLANATION ===\n"
                f"{build_response_rules_explanation(action_ids)}"
            )

            print(
                f"[GeminiWorker] Request #{self._request_count} "
                f"— including response rules explanation."
            )

        if include_memory:
            sections.append(
                f"=== VENUS MEMORY ===\n{self.memory.get_prompt()}"
            )

            print(
                f"[GeminiWorker] Request #{self._request_count} "
                f"— including memory block."
            )

        if user_text:
            sections.append(
                f"=== USER INPUT ===\n{user_text}"
            )

        return "\n\n".join(sections)


# Shared instance used by the rest of the backend.
worker = GeminiWorker()