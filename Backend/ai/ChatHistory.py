"""
ChatHistory.py

In-memory record of this session's conversation, for PanelWindow's
History tab. Deliberately NOT persisted to disk — restart the backend
and it's gone. If that ever needs to change, this is the one place to
add a file-backed store; nothing else should know or care.

`image`, when provided, is kept as the raw PIL.Image object (whatever
was already passed into process_question/GeminiWorker) — not saved to
disk, not converted to anything else. Only PanelWindow ever reads it,
and only to build a QPixmap thumbnail for display. This only covers
the USER's side of the conversation (an image pasted into the input
window); Venus/monitor images go through the separate OPENIMAGE
file-serving pipeline in Server.py and aren't logged here.

Thread safety matters here: add() is called from Flask request
threads and from Orchestrator's worker thread (via queue_response /
process_question in Server.py), while PanelWindow reads/subscribes
from the Qt main thread.
"""

from datetime import datetime
import threading


class ChatHistory:

    def __init__(self):
        self._lock = threading.Lock()
        self._messages = []  # list of {"role", "text", "timestamp", "image"}
        self._listeners = []

    def add(self, role, text, image=None):
        if not text and image is None:
            return

        message = {
            "role": role,
            "text": text or "",
            "timestamp": datetime.now().strftime("%H:%M"),
            "image": image,
        }

        with self._lock:
            self._messages.append(message)
            listeners = list(self._listeners)

        for listener in listeners:
            listener(message)

    def get_all(self):
        with self._lock:
            return list(self._messages)

    def subscribe(self, listener):
        """
        Registers a callable invoked with each new message dict as it's
        added. PanelWindow uses this to append bubbles live rather than
        polling. No unsubscribe path — exactly one PanelWindow exists
        for the process lifetime.
        """
        with self._lock:
            self._listeners.append(listener)


# Shared instance, same pattern as `mood` and `worker` elsewhere.
chat_history = ChatHistory()