"""
on_call_actions/

Registry of "on-call actions" — backend jobs Venus can trigger via a
normal ACTION in her response (see ResponseParser.py), that don't map
to anything Unity actually does. Each one runs on a background thread
once GeminiWorker's response comes back with a matching ACTION (see
Server.py's queue_response/_run_on_call_action), and its result is fed
back to Gemini as a follow-up SYSTEM message so Venus can actually
tell the user what happened.

REMINDER is the one exception to "result is fed back immediately" —
see Reminder.py's docstring for why.

To add a new one:
  1. Write a `def handler(result: dict) -> str` function in its own
     file in this package. `result` is the full parsed response dict
     (see ResponseParser.parse), so the handler can read whatever
     field it needs off it.
  2. Register it below under the ACTION name Gemini will send.
  3. Add that ACTION (and any query field it needs) to
     ResponseParser.py's VALID_ACTIONS and Prompts.py's RESPONSE_RULES.
"""

from on_call_actions.FindFile import find_file
from on_call_actions.KeyboardControl import keyboard_control
from on_call_actions.Reminder import set_reminder

ON_CALL_ACTIONS = {
    "FINDFILE": find_file,
    "KEYBOARDCONTROL": keyboard_control,
    "REMINDER": set_reminder,
}