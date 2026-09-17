"""
Minimal Flask backend for Project Venus (rewrite).

Responsibilities of this file, kept deliberately small:

  1. Expose a health check endpoint so Unity's PythonConnection can
     tell whether the backend is alive.
  2. Expose a /ping endpoint that Unity polls to receive data from
     Python (see PingListener.cs on the Unity side).
  3. Provide a way to actually SEND a ping. Since Unity pulls (polling)
     rather than Python pushing, "sending" means placing a payload in
     a thread-safe slot that the next /ping request picks up.
  4. Own the Orchestrator instance and expose /response — the endpoint
     Unity polls to receive whatever GeminiWorker produced. This is
     the LAST step of the monitor pipeline (see generic_interaction.py):
     internal cooldown -> Orchestrator -> GeminiWorker -> ResponseParser
     -> Orchestrator.on_result -> queue_response() (below) -> /response.
  5. Dispatch "on-call actions" (see on_call_actions/) — backend-only
     jobs (file search, ...) that a response's ACTION can trigger.
     These don't map to anything Unity does, so queue_response() swaps
     the action to NONE before it reaches Unity, runs the job on its
     own thread, and feeds the result back to Gemini as a follow-up
     SYSTEM message once it's done.

Every future capability should follow the same shape: one queue/slot +
one endpoint + one Unity listener script, instead of growing this file
into a monolith.
"""

import threading
import time
from collections import deque

from flask import Flask, jsonify, request, send_file
import uuid
from Orchestrator import Orchestrator, Category
from Monitors.PassiveMonitor import PassiveMonitor
from ai.BootManager import BootManager
from ai.ChatHistory import chat_history
from ai.GeminiWorker import worker
from on_call_actions import ON_CALL_ACTIONS
from on_call_actions.Reminder import persistent_reminder_manager
from one_time_run.DiskInspector import DiskInspect
from one_time_run.HardwareInspector import HardwareInspect
from one_time_run.MemoryCleanupManager import MemoryCleanupCheck
from one_time_run.OneTimeManager import OneTimeManager
from ui.TextInput import start_input_window


app = Flask(__name__)

# ImageHolder.cs fetches images with UnityWebRequestTexture.GetTexture(),
# which needs a full absolute URL, not a path relative to PythonConnection's
# baseUrl (unlike /response and /ask, which Unity already prefixes itself).
# Keep this in sync with baseUrl in PythonConnection.cs if that ever changes.
BASE_URL = "http://127.0.0.1:5000"


@app.route("/health", methods=["GET"])
def health():
    """Used by Unity's PythonConnection to check that the backend is up."""
    return jsonify({"status": "ok"})


# ---------------------------------------------------------------------
# Image serving (Orchestrator -> Unity's ImageHolder)
# ---------------------------------------------------------------------
# A response with action="OPENIMAGE" carries a LOCAL file path
# (image_path) rather than a URL — boredom_monitor.py is the only
# source of that today. Unity can't fetch a Windows filesystem path
# directly, so it's registered here under a one-time id and served
# back over HTTP; the response that actually reaches Unity gets an
# "image" URL instead of the raw path.

_pending_images_lock = threading.Lock()
_pending_images = {}  # image_id -> local file path


def _register_image(path):
    image_id = uuid.uuid4().hex

    with _pending_images_lock:
        _pending_images[image_id] = path

    return image_id



_pending_audio_lock = threading.Lock()
_pending_audio = {}  # audio_id -> local file path


def _register_audio(path):
    audio_id = uuid.uuid4().hex

    with _pending_audio_lock:
        _pending_audio[audio_id] = path

    return audio_id

@app.route("/image/<image_id>", methods=["GET"])
def image(image_id):
    with _pending_images_lock:
        path = _pending_images.pop(image_id, None)

    if not path:
        return "", 404

    return send_file(path, conditional=False)


@app.route("/audio/<audio_id>", methods=["GET"])
def audio(audio_id):
    with _pending_audio_lock:
        path = _pending_audio.pop(audio_id, None)

    if not path:
        return "", 404

    return send_file(path, mimetype="audio/wav", conditional=False)


@app.route("/debug_tts", methods=["GET"])
def debug_tts():
    """
    Bypasses Gemini entirely — synthesizes a line via TTSWorker and
    queues it for Unity exactly like a real response would be, for
    tuning DSP parameters or exercising an ACTION/on-call handler
    without burning a Gemini call. Not part of the normal pipeline;
    remove before shipping.

    command: curl.exe "http://127.0.0.1:5000/debug_tts?text=fine,+I%27ll+remind+you&action=NONE&reminder_query=die&reminder_minutes=1"
    """
    text = request.args.get("text", "Testing testing one two three.")
    action = request.args.get("action", "NONE")

    audio_path = worker.tts.generate_audio(text)

    result = {
        "text": text,
        "action": action,
        "mood_variant": None,
        "mood_shift": None,
        "memory_type": "NONE",
        "memory_text": "NONE",
        "memory_expire": "NONE",
        "image_query": request.args.get("image_query", "NONE"),
        "file_query": request.args.get("file_query", "NONE"),
        "keyboardcontrol_query": request.args.get("keyboardcontrol_query", "NONE"),
        "reminder_query": request.args.get("reminder_query", "NONE"),
        "reminder_minutes": request.args.get("reminder_minutes", "NONE"),
        "audio_path": audio_path,
    }

    result.pop("select_days", None)
    result.pop("reminder_time", None)
    queue_response(result)

    return jsonify({"status": "queued", "text": text, "action": action})

# ---------------------------------------------------------------------
# Response queue (Orchestrator -> Unity)
# ---------------------------------------------------------------------
# A real queue, not a single slot: more than one Venus response can
# legitimately be waiting if Unity is briefly slow to poll. Orchestrator
# already guarantees these arrive one at a time and properly spaced —
# this queue just holds them until Unity asks.

_response_lock = threading.Lock()
_response_queue = deque()


def queue_response(result):
    """
    Registered as Orchestrator's `on_result` callback (see below) — this
    is the "send response to Unity" step of the pipeline. Called
    automatically with whatever an async builder() returned (the parsed
    dict from GeminiWorker.run()); nothing else needs to call this
    directly.

    Also marks a OneTimeManager interaction: any response reaching this
    point — user, monitor, or system check — counts as "something just
    happened", which resets the silence timer those checks wait on.

    If the response's ACTION is an on-call action (see on_call_actions/),
    Unity has nothing to do with it — the action is swapped to NONE
    before this response is queued for Unity, and the actual job runs
    on its own thread (see _run_on_call_action below).
    """
    # Logged first, before anything below mutates `result` — this is
    # Venus's side of the session chat (PanelWindow's History tab).
    # Covers normal replies, monitor comments, and system messages
    # alike, since all of them are things Venus actually said this
    # session. Silent responses (DEADPIXEL, etc.) have empty text and
    # chat_history.add() already no-ops on falsy text/image.
    chat_history.add("venus", result.get("text"))

    image_path = result.pop("image_path", None)
    result["image"] = f"{BASE_URL}/image/{_register_image(image_path)}" if image_path else None

    audio_path = result.pop("audio_path", None)
    result["audio"] = f"{BASE_URL}/audio/{_register_audio(audio_path)}" if audio_path else None

    action = result.get("action")


    if action in ON_CALL_ACTIONS:
        handler = ON_CALL_ACTIONS[action]
        threading.Thread(
            target=_run_on_call_action, args=(handler, action, dict(result)), daemon=True
        ).start()
        result["action"] = "NONE"

    # Backend-only field — never meant for Unity, whether or not an
    # on-call action actually fired this turn.
    result.pop("file_query", None)
    result.pop("reminder_query", None)
    result.pop("reminder_minutes", None)

    with _response_lock:
        _response_queue.append(result)

    print(f"[server] Response queued for Unity: {result}")

    one_time_manager.mark_interaction()


# Minimum seconds between the initial response (the one carrying the
# ACTION) and its follow-up being submitted to Orchestrator. Most
# on-call actions (a Downloads-folder file search, ...) finish in well
# under a second — without this, the follow-up landed on Unity almost
# on top of the first response, overlapping speech bubbles/audio and
# making Venus sound like she found the file suspiciously fast.
ON_CALL_ACTION_MIN_DELAY = 20.0


def _run_on_call_action(handler, action, result):
    """
    Runs a single on-call action (see on_call_actions/) to completion,
    then submits its outcome back to Gemini as a follow-up SYSTEM
    message. Always runs on its own daemon thread — NEVER inside
    Orchestrator's worker thread — because some of these (a full disk
    search) can take a while, and nothing else queued should have to
    wait on that.

    The follow-up itself goes through Orchestrator normally (async,
    Category.SYSTEM), so it's delivered through the usual on_result ->
    queue_response -> /response path, same as anything else. It's held
    back until ON_CALL_ACTION_MIN_DELAY has passed since this thread
    started, regardless of how fast the action itself actually ran.
    """
    started_at = time.time()

    try:
        outcome = handler(result)
    except Exception:
        import traceback
        traceback.print_exc()
        outcome = f"The {action} action failed to run."

    if not outcome: return
    remaining = ON_CALL_ACTION_MIN_DELAY - (time.time() - started_at)
    if remaining > 0:
        time.sleep(remaining)

    def builder():
        return worker.run(user_text=f"[SYSTEM MESSAGE: Result of {action} action: {outcome}]")

    orchestrator.add(Category.SYSTEM, builder)


@app.route("/response", methods=["GET"])
def response():
    with _response_lock:
        pending = _response_queue.popleft() if _response_queue else None

    return jsonify(pending if pending is not None else {})


# ---------------------------------------------------------------------
# Orchestrator + monitors + one-time checks
# ---------------------------------------------------------------------

orchestrator = Orchestrator(on_result=queue_response)

passive_monitor = PassiveMonitor(orchestrator)

one_time_manager = OneTimeManager(
    orchestrator=orchestrator,
    checks=[
        HardwareInspect(),
        DiskInspect(),
        MemoryCleanupCheck(memory_manager=worker.memory),
    ],
)

boot_manager = BootManager()


# ---------------------------------------------------------------------
# Direct user questions (text_input_window.py)
# ---------------------------------------------------------------------

def process_question(text, image=None):
    """
    Injected into text_input_window.py as its `process_question`
    callback. Submits with Category.USER — the highest priority, so a
    typed question always jumps ahead of anything a monitor queued.
    sync=True blocks this call until GeminiWorker actually produces a
    result, since the window doesn't wait for or use the return value
    itself.

    One exception: if BootManager is still waiting for the user's name
    (see boot_manager.py), this ISN'T a normal question — it's the
    answer to the first-boot prompt. Routing it through
    handle_name_answer() instead is what actually resumes Orchestrator;
    witho   ut this check, the app would stay paused forever after first
    boot.

    Unlike async monitor/system requests, a sync request's result is
    NOT passed to Orchestrator's on_result automatically — it's handed
    straight back to this function instead. So delivery to Unity has
    to be done explicitly here, same as it would be anywhere else.
    """
    # Logged as the user's side of the session chat regardless of which
    # branch below actually handles it (normal question or the
    # first-boot name answer) — both are genuinely something the user
    # typed. `image` is whatever was pasted into the input window
    # (see TextInput.py) — PanelWindow renders it as a thumbnail if
    # present. /ask (Unity-triggered, e.g. pokes) also funnels through
    # here with image=None, so poke-generated text ends up logged as
    # "user" too; not worth special-casing for now.
    chat_history.add("user", text, image=image)

    if boot_manager.is_waiting_for_name():
        result = boot_manager.handle_name_answer(orchestrator, text)
        queue_response(result)
        return

    def builder():
        return worker.run(user_text=text, image=image)

    result = orchestrator.add(Category.USER, builder, sync=True)
    queue_response(result)


@app.route("/ask", methods=["POST"])
def ask():
    """
    Generic entry point for anything UNITY wants Venus to react to
    directly — pokes today, any other in-game trigger later. Unity
    decides WHEN to call this and WHAT text to send (e.g. "user is
    poking you on your head"); this route just gets that text into the
    same Category.USER pipeline text_input_window.py already uses, via
    process_question().

    Fires process_question() on a background thread and responds 202
    immediately — same fire-and-forget shape text_input_window.py
    already uses. Unity never waits on THIS call for an answer; it
    always arrives through /response, like everything else.
    """
    data = request.get_json(silent=True) or {}
    text = data.get("text", "")

    if not text:
        return jsonify({"error": "Missing 'text'."}), 400

    threading.Thread(target=process_question, args=(text,), daemon=True).start()

    return jsonify({"status": "queued"}), 202


if __name__ == "__main__":
    orchestrator.start()
    passive_monitor.start()
    one_time_manager.start()

    # Flask needs to run on its own thread: start_input_window (below)
    # blocks the main thread with the Qt event loop until the window is
    # closed, and that has to be the LAST thing called on it.
    flask_thread = threading.Thread(
        target=lambda: app.run(host="127.0.0.1", port=5000, use_reloader=False),
        daemon=True,
    )
    flask_thread.start()

    boot_manager.run(orchestrator, deliver_response=queue_response)

    # If BootManager just paused waiting for a name, the window needs
    # to open immediately — otherwise the user has no way of knowing
    # they're expected to answer. Any other time, it only opens via the
    # hotkey.
    start_input_window(process_question, open_automatically=boot_manager.is_waiting_for_name())

if __name__ == "__main__":
    orchestrator.start()
    passive_monitor.start()
    one_time_manager.start()
    persistent_reminder_manager.start()