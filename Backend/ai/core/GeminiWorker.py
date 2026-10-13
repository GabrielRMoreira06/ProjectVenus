"""
gemini_worker.py

Wraps a single, ongoing Gemini chat session and turns raw model output
into a structured Venus response (text + action + mood shift + memory
operation).

Prompt context levels:
  - Default (every interaction): mood + response FORMAT only.
  - full_context=True: format + rules explanation (descriptions) +
    memory block. Used by the boot message and MeetUserMonitor.

The ACTION list in the format is built from the action ids permitted
for THIS call: a normal call shows the regular catalog minus actions
still locked by XP; a restricted call (allowed_actions) shows only the
given ones.
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
from ai.core.ResponseParser import ResponseParser
from ai.MoodController import mood
from ai.MemoryManager import MemoryManager
from ai.EXPManager import exp_manager
from ai.core.TTSWorker import tts_worker as shared_tts_worker
from ai.tools.ImageSearch import search_image as default_image_search


load_dotenv()

MODEL_NAME = "gemini-3.5-flash-lite"

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

    def run(self, user_text=None, image=None, full_context=False, allowed_actions=None):
        """
        full_context: False (default) sends only mood + response format.
        True also sends the rules explanation and the memory block.

        allowed_actions: None = normal turn (regular catalog minus
        XP-locked actions; a pick is denied after the fact if disabled
        in Preferences or locked). An explicit set restricts the prompt
        to just those actions.
        """
        try:
            self._request_count += 1

            prompt = self._build_prompt(user_text, full_context, allowed_actions)
            print(prompt)
            content = [prompt] if image is None else [prompt, image]

            response = None

            for attempt in range(MAX_RETRIES):
                try:
                    response = self.chat.send_message(content)
                    break

                except Exception as error:
                    error_text = str(error)

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

            if allowed_actions is not None:
                permitted_actions = set(allowed_actions)
            else:
                permitted_actions = {
                    action_id for action_id in preferences.enabled_actions()
                    if exp_manager.is_unlocked("action", action_id)
                }

            if parsed["action"] != "NONE" and parsed["action"] not in permitted_actions:
                denied_action = parsed["action"]
                parsed["action"] = "NONE"
                self._deny_action(denied_action)

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

            if parsed["memory_type"] != "NONE":
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
        print(f"[GeminiWorker] Action '{action}' denied for this request.")

        import sys
        orchestrator = sys.modules["__main__"].orchestrator

        def builder():
            return self.run(user_text=f"[SYSTEM MESSAGE: you tried to use {action} but it was denied.]")

        orchestrator.add(Category.SYSTEM, builder)

    def _resolve_image(self, parsed):
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

    def _build_prompt(self, user_text, full_context, allowed_actions=None):
        if allowed_actions is None:
            action_ids = [a for a in ACTIONS if exp_manager.is_unlocked("action", a)]
        else:
            action_ids = list(allowed_actions)

        sections = [
            f"TIME: {datetime.now().strftime('%H:%M')}",
            f"=== VENUS MOOD ===\n{self.mood.get_prompt()}",
            f"=== RESPONSE RULES ===\n{build_response_rules(action_ids)}",
        ]

        if full_context:
            sections.append(
                f"=== RESPONSE RULES EXPLANATION ===\n"
                f"{build_response_rules_explanation(action_ids)}"
            )
            sections.append(
                f"=== VENUS MEMORY ===\n{self.memory.get_prompt()}"
            )

            print(
                f"[GeminiWorker] Request #{self._request_count} "
                f"— including full context (explanation + memory)."
            )

        if user_text:
            sections.append(
                f"=== INPUT ===\n{user_text}"
            )

        return "\n\n".join(sections)


worker = GeminiWorker()