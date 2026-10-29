"""
generic_interaction.py

A monitor with no metric to watch — it exists purely to vary the kind
of thing Venus says when nothing else has happened in a while. Three
behaviors: recommend a game from Steam, comment on one of their open
windows, or report on system health.

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

GAME RECOMMENDATION: all three steps run inside builder(), so they stay
serialized with every other use of worker.chat. (1) A silent request
goes through the SAME chat session (worker.chat) and asks for a short
Steam search query — no parsing, no TTS, nothing delivered, but the
exchange stays in the session history, so Venus picks with context and
remembers having picked. (2) The query goes to Steam's keyless
storesearch + appdetails endpoints. (3) The game's details are handed to
worker.run() as a normal SYSTEM message.

HEALTH REPORT: CPU%, RAM%, per-partition disk usage, and disk I/O
activity since the last report — all via psutil, no extra
dependencies. GPU and temperature are deliberately left out, same
reasoning as HardwareMonitor.py: no vendor-neutral way to read them
without pulling in something like LibreHardwareMonitor.
"""

import ctypes
import random
import time

import psutil
import requests

from ai.core.GeminiWorker import worker
from Orchestrator import Category
from Monitors.BaseMonitor import BaseMonitor

EXCLUDED_TITLES = {"Program Manager", "Windows Input Experience"}

STEAM_SEARCH_URL = "https://store.steampowered.com/api/storesearch/"
STEAM_DETAILS_URL = "https://store.steampowered.com/api/appdetails"
STEAM_PAGE_URL = "https://store.steampowered.com/app/{}"
STEAM_TIMEOUT = 10      # seconds
STEAM_CANDIDATES = 5    # how many search results to try before giving up
GAME_MEMORY = 30        # how many already-recommended games to remember


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


def search_steam(query, exclude=None):
    """
    Searches the Steam store and returns up to STEAM_CANDIDATES apps
    (dicts with at least "id" and "name"), skipping any whose name is
    in `exclude`.
    """
    exclude = exclude or set()

    response = requests.get(
        STEAM_SEARCH_URL,
        params={"term": query, "l": "english", "cc": "us"},
        timeout=STEAM_TIMEOUT,
    )
    response.raise_for_status()

    items = response.json().get("items", [])
    candidates = [
        item for item in items
        if item.get("type") == "app" and item.get("name") not in exclude
    ]

    return candidates[:STEAM_CANDIDATES]


def fetch_game_details(app_id):
    """Returns Steam's appdetails "data" dict for `app_id`, or None if unavailable."""
    response = requests.get(
        STEAM_DETAILS_URL,
        params={"appids": app_id, "cc": "us", "l": "english"},
        timeout=STEAM_TIMEOUT,
    )
    response.raise_for_status()

    entry = response.json().get(str(app_id), {})

    if not entry.get("success"):
        return None

    return entry.get("data") or None


def format_game_details(app_id, data):
    if data.get("is_free"):
        price = "Free to play"
    else:
        price = data.get("price_overview", {}).get("final_formatted", "unknown")

    lines = [
        f"Name: {data.get('name', 'unknown')}",
        f"Description: {data.get('short_description', 'none')}",
        f"Price: {price}",
    ]

    metacritic = data.get("metacritic", {}).get("score")
    if metacritic:
        lines.append(f"Metacritic: {metacritic}")

    lines.append(f"Steam page: {STEAM_PAGE_URL.format(app_id)}")

    return "\n".join(lines)


class GenericInteractionMonitor(BaseMonitor):

    def __init__(self, orchestrator, interval=2000):
        super().__init__(orchestrator, interval)

        self.behavior_weights = {
            "game": 3,
            "inspect": 3,
            "health_report": 3,
        }

        # Disk I/O counters are cumulative since boot, so the first
        # health report has nothing to compare against — these track
        # the last reading so later reports can show a delta instead.
        self._last_io_counters = None
        self._last_io_time = None

        # Games already recommended, so consecutive recommendations
        # don't repeat.
        self._shown_games = []

    def check(self):
        behavior = self._choose_behavior()

        if behavior == "inspect":
            self._fire_inspect()
        elif behavior == "health_report":
            self._fire_health_report()
        else:
            self._fire_game()

    def _choose_behavior(self):
        behaviors = list(self.behavior_weights.keys())
        weights = list(self.behavior_weights.values())
        return random.choices(behaviors, weights=weights, k=1)[0]

    # ------------------------------------------------------------------
    # Game recommendation
    # ------------------------------------------------------------------

    def _request_game_query(self):
        shown = ", ".join(self._shown_games) or "none"

        prompt = (
            "[SYSTEM MESSAGE: you want to recommend a game to the user. "
            "Reply with ONLY a short Steam store search query (1-3 words): "
            "a specific game title or genre keywords. "
            "Plain text, not the usual response format, no explanation. "
            f"Already recommended, pick something else: {shown}]"
        )

        response = worker.chat.send_message([prompt])

        lines = (response.text or "").strip().splitlines()
        query = lines[0].strip() if lines else ""

        if query.upper().startswith("TEXT:"):
            query = query[5:].strip()

        return query.strip('"')

    def _find_game(self, query):
        for candidate in search_steam(query, exclude=set(self._shown_games)):
            data = fetch_game_details(candidate["id"])

            if data is not None:
                return format_game_details(candidate["id"], data), data.get("name", candidate["name"])

        return None

    def _fire_game(self):
        print("[GenericInteractionMonitor] Looking for a game recommendation.")

        def builder():
            try:
                query = self._request_game_query()

                if not query:
                    print("[GenericInteractionMonitor] Gemini returned no search query, skipping.")
                    return None

                print(f"[GenericInteractionMonitor] Steam query: '{query}'")

                found = self._find_game(query)
            except Exception as e:
                print(f"[GenericInteractionMonitor] Game search failed: {e}")
                return None

            if found is None:
                print(f"[GenericInteractionMonitor] No usable Steam result for '{query}', skipping.")
                return None

            details, name = found

            self._shown_games.append(name)
            self._shown_games = self._shown_games[-GAME_MEMORY:]

            print(f"[GenericInteractionMonitor] Game found:\n{details}")

            return worker.run(
                user_text=f"[SYSTEM MESSAGE: you found this game, comment about it to the user.\n{details} hint: use SHOWIMAGE passing the game name]"
            )

        self.orchestrator.add(Category.MONITOR, builder)

    # ------------------------------------------------------------------
    # Open windows
    # ------------------------------------------------------------------

    def _fire_inspect(self):
        windows = get_open_windows()

        if not windows:
            print("[GenericInteractionMonitor] No windows found, falling back to 'game'.")
            self._fire_game()
            return

        window_list = "\n".join(f"- {title}" for title in windows)
        prompt = f"""=== OPEN WINDOWS ===
{window_list}

[SYSTEM MESSAGE: Venus checked the open windows. Pause the conversation, pick one and comment.]"""

        print("[GenericInteractionMonitor] Commenting on an open window.")

        def builder():
            return worker.run(user_text=prompt)

        self.orchestrator.add(Category.MONITOR, builder)

    # ------------------------------------------------------------------
    # Health report
    # ------------------------------------------------------------------

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