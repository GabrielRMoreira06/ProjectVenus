"""
Reminder.py

Registered as the REMINDER on-call action (see on_call_actions/__init__.py).

Two kinds of reminder, distinguished by SELECT_DAYS:

  - ONE-SHOT (SELECT_DAYS == NONE): the original behavior. Fires once,
    REMINDER_MINUTES from now, via a plain threading.Timer. Does not
    survive a backend restart — if the app closes before it fires,
    it's gone.

  - PERSISTENT (SELECT_DAYS is a list of weekdays, e.g. "1,3,5"): fires
    every REMINDER_TIME (HH:MM, 24h) on each selected day, indefinitely
    — there's no removal path yet, same "left in place" spirit as other
    partial features in this codebase (STEALMOUSE, boredom_monitor's
    SHOWIMAGE serving). Saved to disk (persistent_reminders.json) so it
    survives a restart: PersistentReminderManager reloads it at
    __init__ and keeps checking.

Days use ISO weekday numbering (1=Monday ... 7=Sunday), matching
Python's own datetime.isoweekday() — no separate mapping table needed.

Like FindFile/KeyboardControl, neither path's "result" is ready when
the handler returns — a one-shot fires REMINDER_MINUTES later, a
persistent one just keeps firing indefinitely. Both return None
(fire-and-forget, see Server.py's `if not outcome: return`) — the
reminder's own acknowledgement already happened in that turn's TEXT.

`orchestrator` is imported INSIDE the firing functions, not at module
load time — Server.py imports on_call_actions (and therefore this
file) before orchestrator is constructed, so a top-level import would
be circular. By the time anything actually fires, Server.py has long
finished loading.
"""

import json
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path

from Orchestrator import Category
from ai.GeminiWorker import worker

VALID_DAYS = set(range(1, 8))  # ISO weekday: 1=Monday ... 7=Sunday


def set_reminder(result):
    print("ALARM SET REMINDER", flush=True)
    query = (result.get("reminder_query") or "").strip()
    select_days_raw = (result.get("select_days") or "").strip()
    print(f"[Reminder] query={query!r} select_days={select_days_raw!r}", flush=True)

    if not query or query.lower() == "none":
        return "No reminder text was provided, so no reminder was set."

    if select_days_raw and select_days_raw.upper() != "NONE":
        return _set_persistent_reminder(query, select_days_raw, result)

    return _set_one_shot_reminder(query, result)


# ----------------------------------------------------------------------
# One-shot (original behavior)
# ----------------------------------------------------------------------

def _set_one_shot_reminder(query, result):
    minutes_raw = (result.get("reminder_minutes") or "").strip()

    try:
        minutes = float(minutes_raw)
    except (TypeError, ValueError):
        return f"REMINDER_MINUTES was invalid ('{minutes_raw}'), so no reminder was set."

    if minutes <= 0:
        return "REMINDER_MINUTES must be greater than 0, so no reminder was set."

    timer = threading.Timer(minutes * 60, _fire_one_shot, args=(query,))
    timer.start()
    print(f"[Reminder] one-shot timer started, {minutes} minutes, is_alive={timer.is_alive()}", flush=True)

    return None


def _fire_one_shot(query):
    import sys
    orchestrator = sys.modules["__main__"].orchestrator

    def builder():
        return worker.run(user_text=f"[SYSTEM MESSAGE: Reminder time reached: {query}]")

    orchestrator.add(Category.SYSTEM, builder)


# ----------------------------------------------------------------------
# Persistent / recurring
# ----------------------------------------------------------------------

def _set_persistent_reminder(query, select_days_raw, result):
    time_raw = (result.get("reminder_time") or "").strip()

    try:
        days = {int(d.strip()) for d in select_days_raw.split(",") if d.strip()}
    except ValueError:
        return f"SELECT_DAYS was invalid ('{select_days_raw}'), so no persistent reminder was set."

    if not days or not days.issubset(VALID_DAYS):
        return f"SELECT_DAYS must only contain numbers 1-7 ('{select_days_raw}'), so no persistent reminder was set."

    try:
        datetime.strptime(time_raw, "%H:%M")
    except ValueError:
        return f"REMINDER_TIME was invalid ('{time_raw}'), expected HH:MM — no persistent reminder was set."

    persistent_reminder_manager.add(query, sorted(days), time_raw)
    print(f"[Reminder] persistent reminder added: '{query}' on days {sorted(days)} at {time_raw}", flush=True)

    return None


class PersistentReminderManager:
    """
    Owns every persistent (recurring) reminder. Loads/saves them as a
    flat JSON list so they survive a backend restart, and runs a single
    background thread that wakes up every `poll_interval` seconds to
    check whether any of them are due.

    A reminder is "due" when today's ISO weekday is in its `days` list,
    the current time (HH:MM) matches its `time`, AND it hasn't already
    fired today (`last_fired` != today's date) — that last check is
    what stops it from firing repeatedly for the whole minute the clock
    matches, since poll_interval is much shorter than 60s.
    """

    def __init__(self, state_file="persistent_reminders.json", poll_interval=30):
        self.state_file = Path(state_file)
        self.poll_interval = poll_interval
        self._lock = threading.Lock()
        self.reminders = self._load()
        self._running = False

    def add(self, query, days, time_str):
        entry = {
            "id": uuid.uuid4().hex[:8],
            "query": query,
            "days": days,
            "time": time_str,
            "last_fired": None,
        }

        with self._lock:
            self.reminders.append(entry)
            self._save()

    def start(self):
        self._running = True
        threading.Thread(target=self._loop, daemon=True, name="PersistentReminderManager").start()

    def stop(self):
        self._running = False

    def _loop(self):
        while self._running:
            time.sleep(self.poll_interval)
            self._check_due()

    def _check_due(self):
        now = datetime.now()
        today_iso_weekday = now.isoweekday()
        today_str = now.strftime("%Y-%m-%d")
        current_time = now.strftime("%H:%M")

        with self._lock:
            due = [
                r for r in self.reminders
                if today_iso_weekday in r["days"]
                and r["time"] == current_time
                and r["last_fired"] != today_str
            ]

            for reminder in due:
                reminder["last_fired"] = today_str

            if due:
                self._save()

        for reminder in due:
            self._fire(reminder)

    def _fire(self, reminder):
        import sys
        orchestrator = sys.modules["__main__"].orchestrator

        print(f"[PersistentReminderManager] Firing: '{reminder['query']}'", flush=True)

        def builder():
            return worker.run(
                user_text=f"[SYSTEM MESSAGE: Recurring reminder time reached: {reminder['query']}]"
            )

        orchestrator.add(Category.SYSTEM, builder)

    def _load(self):
        if not self.state_file.exists():
            return []

        try:
            with open(self.state_file, "r", encoding="utf-8") as f:
                content = f.read().strip()
                return json.loads(content) if content else []
        except (json.JSONDecodeError, OSError):
            print(f"[PersistentReminderManager] '{self.state_file}' is empty or corrupted — starting with no persistent reminders.")
            return []

    def _save(self):
        with open(self.state_file, "w", encoding="utf-8") as f:
            json.dump(self.reminders, f, ensure_ascii=False, indent=4)


# Shared instance, same pattern as `worker`/`mood` elsewhere. Server.py
# calls .start() on this at boot, alongside orchestrator/passive_monitor/
# one_time_manager.
persistent_reminder_manager = PersistentReminderManager()