"""
Reminder.py

Registered as the REMINDER on-call action (see on_call_actions/__init__.py).

Unlike FindFile/KeyboardControl, the "result" of this action isn't
ready when the handler returns — it's ready REMINDER_MINUTES later.
So this handler doesn't return a string for Server.py's normal
on-call follow-up path; it starts a threading.Timer and returns None
(fire-and-forget, no immediate follow-up — see
Server.py's `if not outcome: return`). The reminder's own
acknowledgement already happened in that turn's TEXT.

When the timer fires, _fire_reminder submits a fresh worker.run() call
through the same Orchestrator every other request goes through, so it
can't land on top of a live user message. `orchestrator` is imported
INSIDE _fire_reminder, not at module load time — Server.py imports
on_call_actions (and therefore this file) before orchestrator is
constructed, so a top-level import would be circular. By the time a
timer actually fires, Server.py has long finished loading.
"""

import threading

from Orchestrator import Category
from ai.GeminiWorker import worker


def set_reminder(result):
    print("ALARM SET REMINDER", flush=True)
    query = (result.get("reminder_query") or "").strip()
    minutes_raw = (result.get("reminder_minutes") or "").strip()
    print(f"[Reminder] query={query!r} minutes_raw={minutes_raw!r}", flush=True)

    if not query or query.lower() == "none":
        return "No reminder text was provided, so no reminder was set."

    try:
        minutes = float(minutes_raw)
    except (TypeError, ValueError):
        return f"REMINDER_MINUTES was invalid ('{minutes_raw}'), so no reminder was set."

    if minutes <= 0:
        return "REMINDER_MINUTES must be greater than 0, so no reminder was set."

    timer = threading.Timer(minutes * 60, _fire_reminder, args=(query,))
    timer.start()
    print(f"[Reminder] timer started, is_alive={timer.is_alive()}", flush=True)

    return None


def _fire_reminder(query):
    import sys
    orchestrator = sys.modules["__main__"].orchestrator

    def builder():
        return worker.run(user_text=f"[SYSTEM MESSAGE: Reminder time reached: {query}]")

    orchestrator.add(Category.SYSTEM, builder)