"""
generic_interaction.py

A monitor with no metric to watch — it exists purely to vary the kind
of thing Venus says when nothing else has happened in a while. Three
behaviors: browse the news, comment on one of their open windows, or
report on system health.

This is the reference example of the full pipeline every monitor
should follow:

  1. INTERNAL COOLDOWN — BaseMonitor's own `interval` timer decides
     when this monitor is even allowed to consider firing again.
  2. ORCHESTRATOR — `check()` never calls Gemini itself. It builds a
     zero-argument `builder` function and hands it to
     `orchestrator.add(category, builder)`. From there, Orchestrator
     decides WHEN builder() actually runs, based on priority
     (Category) and the GLOBAL cooldown (min_delivery_spacing) shared
     across every monitor and the user.
  3. GEMINI WORKER — when it's this request's turn, builder() calls
     `worker.run(...)`, which sends the message to the ongoing Gemini
     chat session.
  4. RESPONSE PARSER — `worker.run()` already parses the raw model
     text into a structured dict before returning it. Nothing here
     touches ResponseParser directly — that's an implementation detail
     of GeminiWorker, not of the monitor.
  5. SEND TO UNITY — builder()'s return value is handed to
     Orchestrator's `on_result` callback, wired up once in server.py to
     queue the response for Unity to pick up. This monitor never talks
     to Unity, or even needs to know delivery exists.

NEWS BROWSING: pulls the Google News RSS feed for technology and hands
three headlines to Gemini. The feed is fetched inside builder() (not in
check()) so the headlines are as fresh as possible at delivery time and
a slow network never blocks the monitor loop.

HEALTH REPORT: CPU%, RAM%, per-partition disk usage, and disk I/O
activity since the last report — all via psutil, no extra
dependencies. GPU and temperature are deliberately left out, same
reasoning as HardwareMonitor.py: no vendor-neutral way to read them
without pulling in something like LibreHardwareMonitor.
"""

import ctypes
import random
import time
import urllib.request

import feedparser
import psutil

from ai.core.GeminiWorker import worker
from Orchestrator import Category
from Monitors.BaseMonitor import BaseMonitor

EXCLUDED_TITLES = {"Program Manager", "Windows Input Experience"}

NEWS_URL = "https://news.google.com/rss/search?q=technology&hl=en-US&gl=US&ceid=US:en"
NEWS_TIMEOUT = 10        # seconds
NEWS_POOL_SIZE = 15      # how many top entries to pick from
NEWS_TITLES_TO_SEND = 3
NEWS_MEMORY = 30         # how many already-shown titles to remember


def get_open_windows():
    """
    Returns the titles of every visible open window on the system —
    gives Gemini a list of "things it could comment on". Only titles,
    never window content (that was tried via pywinauto and dropped:
    poor results on most modern apps, which don't expose content
    through Windows accessibility APIs).
    """
    windows = []

    def callback(hwnd, lparam):
        if not ctypes.windll.user32.IsWindowVisible(hwnd):
            return True

        length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
        if length == 0:
            return True

        buffer = ctypes.create_unicode_buffer(length + 1)
        ctypes.windll.user32.GetWindowTextW(hwnd, buffer, length + 1)
        title = buffer.value.strip()

        if title and title not in EXCLUDED_TITLES:
            windows.append(title)

        return True

    enum_windows_proc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_int, ctypes.c_int)
    ctypes.windll.user32.EnumWindows(enum_windows_proc(callback), 0)

    seen = set()
    return [w for w in windows if not (w in seen or seen.add(w))]


def fetch_news_titles(exclude=None, count=NEWS_TITLES_TO_SEND):
    """
    Browses the Google News technology feed and returns `count`
    headlines picked at random from the top results, skipping any in
    `exclude` (titles already shown recently). Returns an empty list on
    any network/parse failure.

    The feed is downloaded with urllib so a timeout can be enforced
    (feedparser.parse(url) has none), then the raw bytes are handed to
    feedparser for parsing.
    """
    exclude = exclude or set()

    try:
        request = urllib.request.Request(NEWS_URL, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(request, timeout=NEWS_TIMEOUT) as response:
            raw = response.read()

        feed = feedparser.parse(raw)
    except Exception as e:
        print(f"[GenericInteractionMonitor] News fetch failed: {e}")
        return []

    titles = [entry.title.strip() for entry in feed.entries[:NEWS_POOL_SIZE] if getattr(entry, "title", "")]
    fresh = [t for t in titles if t not in exclude]

    # If everything in the pool was already shown, reuse the pool
    # rather than returning nothing.
    pool = fresh if len(fresh) >= count else titles

    if not pool:
        return []

    return random.sample(pool, min(count, len(pool)))


class GenericInteractionMonitor(BaseMonitor):

    def __init__(self, orchestrator, interval=2000):
        super().__init__(orchestrator, interval)

        self.behavior_weights = {
            "browse": 3,
            "inspect": 3,
            "health_report": 3,
        }

        # Disk I/O counters are cumulative since boot, so the first
        # health report has nothing to compare against — these track
        # the last reading so later reports can show a delta instead.
        self._last_io_counters = None
        self._last_io_time = None

        # Headlines already sent to Gemini, so consecutive browses
        # don't repeat the same news.
        self._shown_titles = []

    def check(self):
        behavior = self._choose_behavior()

        if behavior == "inspect":
            self._fire_inspect()
        elif behavior == "health_report":
            self._fire_health_report()
        else:
            self._fire_ask()

    def _choose_behavior(self):
        behaviors = list(self.behavior_weights.keys())
        weights = list(self.behavior_weights.values())
        return random.choices(behaviors, weights=weights, k=1)[0]

    def _fire_ask(self):
        print("[GenericInteractionMonitor] browsing news.")

        def builder():
            titles = fetch_news_titles(exclude=set(self._shown_titles))

            if not titles:
                print("[GenericInteractionMonitor] No news available, nothing to report.")
                return worker.run(user_text="[SYSTEM MESSAGE: nothing to report.]")

            self._shown_titles.extend(titles)
            self._shown_titles = self._shown_titles[-NEWS_MEMORY:]

            headline_list = "\n".join(f"- {title}" for title in titles)
            prompt = f""" [SYSTEM MESSAGE: Venus were browsing the internet and saw these headlines, pause the conversation and comment to User:
{headline_list}]
"""


            print(f"[GenericInteractionMonitor] Headlines:\n{headline_list}")

            return worker.run(user_text=prompt)

        self.orchestrator.add(Category.MONITOR, builder)

    def _fire_inspect(self):
        windows = get_open_windows()

        if not windows:
            print("[GenericInteractionMonitor] No windows found, falling back to 'ask'.")
            self._fire_ask()
            return

        window_list = "\n".join(f"- {title}" for title in windows)
        prompt = f"""=== OPEN WINDOWS ===
{window_list}

[SYSTEM MESSAGE: Venus checked the open windows. Pause the conversation, pick one and comment.]"""

        print("[GenericInteractionMonitor] Commenting on an open window.")

        def builder():
            return worker.run(user_text=prompt)

        self.orchestrator.add(Category.MONITOR, builder)

    def _fire_health_report(self):
        summary = self._collect_health_summary()

        print(f"[GenericInteractionMonitor] Reporting on system health:\n{summary}")

        prompt = f"""=== SYSTEM HEALTH ===
{summary}

[SYSTEM MESSAGE: Venus just checked her system's vitals. Pause the conversation and comment on it.]"""

        def builder():
            return worker.run(user_text=prompt)

        self.orchestrator.add(Category.MONITOR, builder)

    def _collect_health_summary(self):
        cpu = psutil.cpu_percent(interval=1)
        ram = psutil.virtual_memory().percent

        return (
            f"CPU: {cpu:.0f}%\n"
            f"RAM: {ram:.0f}%\n"
            f"Disk usage: {self._disk_usage_summary()}\n"
            f"Disk activity: {self._disk_activity_summary()}"
        )

    def _disk_usage_summary(self):
        lines = []

        for partition in psutil.disk_partitions(all=False):
            if "cdrom" in partition.opts or partition.fstype == "":
                continue

            try:
                usage = psutil.disk_usage(partition.mountpoint)
                lines.append(f"{partition.mountpoint} at {usage.percent:.0f}%")
            except (PermissionError, OSError):
                continue

        return ", ".join(lines) if lines else "unavailable"

    def _disk_activity_summary(self):
        counters = psutil.disk_io_counters()
        if counters is None:
            return "unavailable"

        now = time.time()

        if self._last_io_counters is None:
            self._last_io_counters = counters
            self._last_io_time = now
            return "no prior reading to compare against yet"

        read_mb = (counters.read_bytes - self._last_io_counters.read_bytes) / (1024 ** 2)
        write_mb = (counters.write_bytes - self._last_io_counters.write_bytes) / (1024 ** 2)

        self._last_io_counters = counters
        self._last_io_time = now

        return f"{read_mb:.1f}MB read / {write_mb:.1f}MB written since last check"