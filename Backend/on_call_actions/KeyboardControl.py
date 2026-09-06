"""
KeyboardControl.py

Types text on the user's keyboard via pyautogui, wherever keyboard
focus currently is on the desktop. Registered as the KEYBOARDCONTROL
on-call action (see on_call_actions/__init__.py).

pyautogui.write() is deliberately slow (0.3s per character) so
keystrokes land like a human typing rather than pasting instantly.
Like find_file(), this handler is slow-tolerant by design: Server.py
always runs it on its own thread, never inside Orchestrator's worker
thread, so typing out a long string doesn't stall anything else
queued up behind it.
"""

import pyautogui


def keyboard_control(result):
    text = (result.get("keyboardcontrol_query") or "").strip()

    if not text or text.lower() == "none":
        return "No text was provided, so nothing was typed."

    try:
        pyautogui.write(text, interval=0.1)
    except Exception as error:
        return f"Failed to type text: {error}"

    return None  # success — nothing worth telling Gemini about