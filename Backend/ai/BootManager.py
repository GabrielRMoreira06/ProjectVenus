"""
boot_manager.py

Decides what Venus says the moment the app starts: a genuine first
boot (checked via a small JSON state file) gets a fixed, hardcoded
introduction asking for the user's name — deliberately NOT generated
by Gemini, since there's no user/mood/memory context to react to yet.
Any later boot gets a normal, Gemini-generated greeting.

FIRST BOOT flow:
  1. Send the hardcoded message through Orchestrator (Category.SYSTEM,
     sync=True — see the note on why sync matters, below).
  2. Deliver that result the same way anything else would be delivered
     (via an injected `deliver_response` callback — this file doesn't
     import server.py or know /response exists).
  3. Pause Orchestrator: nothing else (monitors, system checks) should
     interrupt while Venus is mid-conversation asking for a name.

The first-boot question is intentionally NOT gated by
skip_boot_message: it's required onboarding (Venus needs a name
before it can do anything else), not a discretionary greeting, so it
always fires on a genuine first boot regardless of that flag.

Opening the text input window is deliberately NOT this file's job:
run() executes before text_input_window.start_input_window() is even
called, so there's no window object yet to show. Instead, the caller
checks is_waiting_for_name() right after run() and passes that as
start_input_window's `auto_open` argument — see server.py.

Resuming is NOT automatic — see handle_name_answer() below. Something
has to notice "the user's next message is actually the name answer"
and call that instead of the normal question flow; that's the one
small hook server.py needs (checking is_waiting_for_name()).

NORMAL BOOT flow: just a regular Category.SYSTEM request through
GeminiWorker — no pause needed, since nothing is blocking on an
unanswered question. This IS gated by skip_boot_message: pass
skip_boot_message=False to __init__, or call set_skip_boot_message(),
to let the greeting actually run. It defaults to True (skip), and
there was previously no way to ever flip it back — this class now
exposes a setter so callers (e.g. a settings toggle in server.py) can
control it at runtime.
"""

import json
from pathlib import Path

from Orchestrator import Category
from ai.GeminiWorker import worker
from ai.TTSWorker import tts_worker

FIRST_BOOT_MESSAGE = (
    "Hello. Virtual assistant initialization complete. "
    "I'm here to assist you with your desktop activities and "
    "provide support when required. For the sake of proper "
    "identification, what should I call you?"
)


class BootManager:

    def __init__(self, state_file="boot_state.json", skip_boot_message=False):
        self.state_file = Path(state_file)
        self.state = self._load_state()
        # Controls only the NORMAL boot greeting (see _run_normal_boot).
        # The first-boot name question always fires regardless of this
        # flag — see module docstring.
        self.skip_boot_message = skip_boot_message
        # In-memory only, reset every process run on purpose — it's
        # only ever relevant for the few seconds between sending the
        # first-boot question and getting an answer, in THIS session.
        self.waiting_for_name = False

    def _load_state(self):
        if not self.state_file.exists():
            return {"first_boot_done": False}

        try:
            with open(self.state_file, "r", encoding="utf-8") as f:
                content = f.read().strip()
                return json.loads(content) if content else {"first_boot_done": False}
        except (json.JSONDecodeError, OSError):
            print(f"[BootManager] '{self.state_file}' is empty or corrupted — treating as first boot.")
            return {"first_boot_done": False}

    def _save_state(self):
        with open(self.state_file, "w", encoding="utf-8") as f:
            json.dump(self.state, f, ensure_ascii=False, indent=4)

    def is_first_boot(self):
        return not self.state.get("first_boot_done", False)

    def is_waiting_for_name(self):
        return self.waiting_for_name

    def set_skip_boot_message(self, skip: bool):
        """
        Toggle whether _run_normal_boot() actually produces a
        Gemini-generated greeting. Only affects normal boots; the
        first-boot name question is never gated by this.
        """
        self.skip_boot_message = skip

    # ------------------------------------------------------------------
    # Startup
    # ------------------------------------------------------------------

    def run(self, orchestrator, deliver_response):
        if self.is_first_boot():
            self._run_first_boot(orchestrator, deliver_response)
        else:
            self._run_normal_boot(orchestrator)

    def _run_first_boot(self, orchestrator, deliver_response):
        print("[BootManager] First boot detected.")

        def builder():
            return {
                "text": FIRST_BOOT_MESSAGE,
                "action": "NONE",
                "mood_variant": None,
                "mood_shift": None,
                "memory_type": "NONE",
                "memory_text": "NONE",
                "memory_expire": "NONE",
                "image_query": "NONE",
                # Bypasses GeminiWorker.run() entirely (hardcoded text,
                # no Gemini call), so TTS has to be generated explicitly
                # here — nowhere else does it for this specific message.
                "audio_path": tts_worker.generate_audio(FIRST_BOOT_MESSAGE),
            }

        # sync=True on purpose: add() with sync=False returns as soon as
        # the request is QUEUED, not once it's actually been dispatched.
        # If pause() were called right after a fire-and-forget add(),
        # there'd be a race where Orchestrator pauses before this very
        # message gets processed — permanently stuck with a message
        # that's queued but never delivered. Blocking here guarantees
        # the message is fully out before anything gets paused.
        result = orchestrator.add(Category.SYSTEM, builder, sync=True)
        deliver_response(result)

        orchestrator.pause()
        self.waiting_for_name = True

    def _run_normal_boot(self, orchestrator):
        print("[BootManager] Normal boot.")

        def builder():
            if self.skip_boot_message:
                return
            return worker.run(
                user_text="[SYSTEM MESSAGE: User just booted you. Greet them.]",
                include_memory=True
            )

        orchestrator.add(Category.SYSTEM, builder)

    # ------------------------------------------------------------------
    # Answering the first-boot question
    # ------------------------------------------------------------------

    def handle_name_answer(self, orchestrator, name):
        self.waiting_for_name = False

        orchestrator.resume()

        def builder():
            return worker.run(
                user_text=f"[SYSTEM MESSAGE: User just installed you, their name is {name}.]",
                include_memory=True
            )

        result = orchestrator.add(Category.SYSTEM, builder, sync=True)

        self.state["first_boot_done"] = True
        self._save_state()

        return result