"""
Notepad.py

Registered as the NOTEPAD on-call action (see on_call_actions/__init__.py).

Reads whatever's currently saved in the scratchpad notepad and hands
it back as a follow-up SYSTEM message — same minimal shape as
find_file()/keyboard_control(): no internal threading, Server.py
already runs this on its own thread.

AUTOSAVE_PATH must match ui/Notepad.py's AUTOSAVE_PATH — both point at
the same file, that file is the single source of truth for notepad
content.
"""

from pathlib import Path

AUTOSAVE_PATH = Path("notepad_autosave.txt")


def read_notepad(result):
    if not AUTOSAVE_PATH.exists():
        return "The notepad is empty."

    try:
        content = AUTOSAVE_PATH.read_text(encoding="utf-8").strip()
    except OSError as error:
        return f"Failed to read the notepad: {error}"

    if not content:
        return "The notepad is empty."

    return f"Current notepad content:\n{content}"