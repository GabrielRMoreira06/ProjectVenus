"""
Orchestrator.py

Single serialization point for every request Venus needs to process
(user questions, system checks, monitor-triggered comments, ...).

One worker thread processes one request at a time, in priority order,
with a minimum spacing enforced between deliveries. Every request
declares a `category`, which sets both its priority and its log label.

Sync requests that time out on the caller's side are marked
"abandoned": the builder still runs to completion, and its result is
delivered through on_result instead of being dropped.
"""

import heapq
import itertools
import threading
import time


class Category:
    USER = "user"
    SYSTEM = "system"
    MONITOR = "monitor"

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

    def __init__(self, on_result=None, min_delivery_spacing=3.0):
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
        with self._new_item:
            self._paused = True

        print("[Orchestrator] Paused.")

    def resume(self):
        with self._new_item:
            self._paused = False
            self._new_item.notify_all()

        print("[Orchestrator] Resumed.")

    def add(self, category, builder, sync=False, timeout=120):
        """
        sync=False: returns None immediately; the result goes to on_result.
        sync=True: blocks until processed and returns the result. If
        `timeout` elapses first, TimeoutError is raised in the caller,
        but the request is NOT lost — its result is delivered through
        on_result once it finishes.
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
            with self._lock:
                if not event.is_set():
                    request.abandoned = True
                    print(f"[Orchestrator] Sync '{category}' timed out after {timeout}s "
                          f"(paused={self._paused}, queued={len(self._queue)}) — "
                          f"result will be delivered via on_result.")
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
        waited = time.time() - request.queued_at
        print(f"[Orchestrator] Processing '{request.category}' (waited {waited:.1f}s in queue).")

        started = time.time()

        try:
            result = request.builder()
        except Exception as error:
            import traceback
            traceback.print_exc()

            request.error = error
            result = None

        print(f"[Orchestrator] '{request.category}' builder took {time.time() - started:.1f}s.")

        self._last_delivery = time.time()

        if request.sync:
            with self._lock:
                request.result = result
                abandoned = request.abandoned
                if not abandoned:
                    request.event.set()

            if abandoned and result is not None and self.on_result is not None:
                self.on_result(result)

            return

        if result is not None and self.on_result is not None:
            self.on_result(result)


class _Request:
    __slots__ = ("category", "builder", "sync", "event", "result", "error", "abandoned", "queued_at")

    def __init__(self, category, builder, sync, event):
        self.category = category
        self.builder = builder
        self.sync = sync
        self.event = event
        self.result = None
        self.error = None
        self.abandoned = False
        self.queued_at = time.time()