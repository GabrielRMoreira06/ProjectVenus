"""
Orchestrator.py

Single serialization point for every request Venus needs to process
(user questions, system checks, monitor-triggered comments, ...).

Why this exists:
  - The AI chat session is a single, shared conversation — sending two
    messages to it at the same time could interleave turns or corrupt
    the history.
  - Only one thing should ever be "in flight" toward the user (one
    speech bubble, one audio clip) at a time.

This module solves both problems with a single worker thread that
processes one request at a time, in priority order, with a minimum
spacing enforced between deliveries.

Every request submitted via `add()` must declare a `category`. The
category is used for two things at once:
  1. PRIORITY — determines processing order (user requests always jump
     ahead of system/monitor ones).
  2. LABEL — identifies the request in logs.
There is no separate priority argument to keep in sync with a label —
category is the single source of truth for both.
"""

import heapq
import itertools
import threading
import time


class Category:
    """
    Built-in categories and their processing priority (lower runs
    first). Add new categories here as new request sources are
    introduced — each one just needs a priority tier.
    """
    USER = "user"        # direct question typed/spoken by the user
    SYSTEM = "system"    # boot message, one-time checks (hardware, disk...)
    MONITOR = "monitor"  # passive monitors (idle, mood, hardware alerts...)

    _PRIORITIES = {
        USER: 0,
        SYSTEM: 1,
        MONITOR: 2,
    }

    @classmethod
    def priority_of(cls, category):
        if category not in cls._PRIORITIES:
            raise ValueError(
                f"Unknown category '{category}'. "
                f"Known categories: {sorted(cls._PRIORITIES)}"
            )
        return cls._PRIORITIES[category]


class Orchestrator:
    """
    Sole manager of the request queue. Callers submit work via `add()`;
    a background thread pulls requests in priority order and runs them
    one at a time, never in parallel.
    """

    def __init__(self, on_result=None, min_delivery_spacing=3.0):
        """
        on_result: called with the return value of any ASYNC request's
        builder once it finishes. Sync requests (see add(..., sync=True))
        return their result directly to the caller instead of going
        through this callback.

        min_delivery_spacing: minimum seconds enforced between the end
        of one request and the start of the next, so deliveries never
        stack on top of each other on the receiving end (Unity).
        """
        self.on_result = on_result
        self.min_delivery_spacing = min_delivery_spacing

        self._queue = []  # heap of (priority, seq, request)
        self._counter = itertools.count()
        self._lock = threading.Lock()
        self._new_item = threading.Condition(self._lock)

        self._last_delivery = 0.0
        self._running = False
        self._paused = False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start(self):
        self._running = True
        threading.Thread(target=self._loop, daemon=True, name="Orchestrator").start()

    def stop(self):
        self._running = False
        with self._new_item:
            self._new_item.notify_all()

    def pause(self):
        """
        Halts dispatch: nothing new starts running until resume() is
        called, no matter what's sitting in the queue or gets added
        while paused. Requests can still be queued during a pause —
        they just wait. Used for things like the first-boot name
        question, where nothing else should interrupt until it's
        answered.
        """
        with self._new_item:
            self._paused = True

        print("[Orchestrator] Paused.")

    def resume(self):
        with self._new_item:
            self._paused = False
            self._new_item.notify_all()

        print("[Orchestrator] Resumed.")

    def add(self, category, builder, sync=False, timeout=60):
        """
        Submits a request to the queue.

        category (required): one of the Category constants (or a custom
        string registered in Category._PRIORITIES). Determines both the
        processing order and the label used in logs.

        builder: a zero-argument function that performs the actual work
        (call the AI, generate audio, capture the screen, ...) and
        returns a result. Passed as a function — not already executed —
        so the work only starts once it's actually this request's turn.
        This is what guarantees only one builder ever runs at a time.

        sync: if True, blocks the calling thread until the request is
        processed and returns the result directly. Any exception raised
        by builder is re-raised here, in the caller's thread. Use this
        for requests that need an immediate answer (e.g. an HTTP route
        that must respond with a result).
        If False (default), returns immediately (None) and the result,
        once ready, is delivered asynchronously via on_result. Use this
        for anything that doesn't have a caller waiting on the spot
        (monitors, background checks).

        timeout: only used when sync=True — seconds to wait before
        raising TimeoutError if the request hasn't been processed yet.
        """
        priority = Category.priority_of(category)

        event = threading.Event() if sync else None
        request = _Request(category=category, builder=builder, sync=sync, event=event)

        with self._new_item:
            heapq.heappush(self._queue, (priority, next(self._counter), request))
            self._new_item.notify_all()

        if not sync:
            return None

        if not event.wait(timeout=timeout):
            raise TimeoutError(f"Request '{category}' was not processed in time.")

        if request.error is not None:
            raise request.error

        return request.result

    # ------------------------------------------------------------------
    # Worker
    # ------------------------------------------------------------------

    def _loop(self):
        while self._running:
            request = self._next_request()

            if request is None:
                continue

            self._respect_spacing()
            self._process(request)

    def _next_request(self):
        with self._new_item:
            while self._running and (self._paused or not self._queue):
                self._new_item.wait(timeout=1.0)

            if not self._running or self._paused or not self._queue:
                return None

            _, _, request = heapq.heappop(self._queue)
            return request

    def _respect_spacing(self):
        elapsed = time.time() - self._last_delivery
        remaining = self.min_delivery_spacing - elapsed

        if remaining > 0:
            time.sleep(remaining)

    def _process(self, request):
        print(f"[Orchestrator] Processing '{request.category}'.")

        try:
            result = request.builder()
        except Exception as error:
            import traceback
            traceback.print_exc()

            request.error = error
            result = None

        self._last_delivery = time.time()

        if request.sync:
            request.result = result
            request.event.set()
            return

        if result is not None and self.on_result is not None:
            self.on_result(result)


class _Request:
    __slots__ = ("category", "builder", "sync", "event", "result", "error")

    def __init__(self, category, builder, sync, event):
        self.category = category
        self.builder = builder
        self.sync = sync
        self.event = event
        self.result = None
        self.error = None