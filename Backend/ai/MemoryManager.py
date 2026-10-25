"""
memory_manager.py

Persists long-term information about the user across sessions: facts,
memories (dated events), and daily summaries (one per calendar day,
appended to on every update). FACT/MEMORY entries get an auto-generated
id and can optionally expire; entries with no expiration are kept forever.

The Memories page (ui/pages/MemoriesPage.py) reads and edits entries
through list_entries/update_entry/delete_entry and refreshes itself via
subscribe() — listeners are called from whatever thread made the change.
"""

import json
import os
import threading
import uuid
from datetime import datetime, timedelta
from pathlib import Path

from config import DATA_DIR, STATE_DIR

EXPIRATION_DURATIONS = {
    "6HOURS": timedelta(hours=6),
    "1DAY": timedelta(days=1),
    "1WEEK": timedelta(weeks=1),
    "1MONTH": timedelta(days=30),
}

VALID_TYPES = ("FACT", "MEMORY", "DAILYSUMMARY")
CATEGORIES = ("memories", "facts", "daily_summaries")

DAILY_SUMMARIES_IN_PROMPT = 7  # today + previous 6 days
DAILY_SUMMARY_RETENTION = timedelta(weeks=1)
DAILY_SUMMARY_MAX_CHARS = 1200


class MemoryManager:

    def __init__(self, file_path=STATE_DIR / "memory.json"):
        path = Path(file_path)
        self.file_path = path if path.is_absolute() else DATA_DIR / path
        self._lock = threading.RLock()
        self._listeners = []
        self.memory = self._load()
        print(f"[MemoryManager] Using '{self.file_path}'.")

    # ------------------------------------------------------------------
    # Change notifications
    # ------------------------------------------------------------------

    def subscribe(self, listener):
        """listener() is called after any change to the stored entries."""
        self._listeners.append(listener)

    def _notify(self):
        for listener in list(self._listeners):
            try:
                listener()
            except Exception:
                import traceback
                traceback.print_exc()

    # ------------------------------------------------------------------
    # Prompt
    # ------------------------------------------------------------------

    def get_prompt(self):
        with self._lock:
            facts = "\n".join(self._format_item(item) for item in self.memory["facts"])
            memories = "\n".join(self._format_item(item) for item in self.memory["memories"])
            daily_summaries = self._format_daily_summaries()

        return f"""
FACTS:
{facts}

MEMORIES (with date/time/day of week, so you can notice routine patterns):
{memories}

DAILY SUMMARIES (most recent days, today's first; sending DAILYSUMMARY appends to today's entry):
{daily_summaries}
"""

    def _format_daily_summaries(self):
        today = datetime.now().strftime("%Y-%m-%d")
        dates = sorted(self.memory["daily_summaries"].keys(), reverse=True)[:DAILY_SUMMARIES_IN_PROMPT]

        if not dates:
            return "(none yet)"

        lines = []
        for date in dates:
            parsed = datetime.strptime(date, "%Y-%m-%d")
            label = f"{parsed.strftime('%d/%m/%Y, %A')}{' - TODAY' if date == today else ''}"
            lines.append(f"- [{label}] {self.memory['daily_summaries'][date]['text']}")

        return "\n".join(lines)

    def _format_item(self, item):
        created_at = self._parse_created_at(item.get("created_at"))

        if created_at is None:
            return f"- {item['text']}"

        date = created_at.strftime("%d/%m/%Y")
        time = created_at.strftime("%H:%M")
        weekday = created_at.strftime("%A")

        return f"- {item['text']} ({date}, {time}, {weekday})"

    def _parse_created_at(self, value):
        if not value:
            return None
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _load(self):
        data = {}

        if self.file_path.exists():
            try:
                content = self.file_path.read_text(encoding="utf-8").strip()
                data = json.loads(content) if content else {}
            except (json.JSONDecodeError, OSError):
                backup = self.file_path.with_name(self.file_path.name + ".corrupt")
                print(f"[MemoryManager] '{self.file_path}' is corrupted — moved to '{backup}', starting empty.")
                try:
                    os.replace(self.file_path, backup)
                except OSError:
                    pass
                data = {}
        else:
            print(f"[MemoryManager] '{self.file_path}' not found — starting empty.")

        data.setdefault("facts", [])
        data.setdefault("memories", [])
        data.setdefault("daily_summaries", {})
        data.pop("habits", None)  # dropped category

        return data

    def _save(self):
        temp_path = self.file_path.with_name(self.file_path.name + ".tmp")

        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(self.memory, f, ensure_ascii=False, indent=4)
            f.flush()
            os.fsync(f.fileno())

        os.replace(temp_path, self.file_path)

    # ------------------------------------------------------------------
    # Saving (from Gemini responses)
    # ------------------------------------------------------------------

    def save(self, entry_type, text, expires_in="NONE"):
        if entry_type not in VALID_TYPES:
            print(f"[MemoryManager] Unknown MEMORY_TYPE: '{entry_type}' — ignoring.")
            return

        with self._lock:
            if entry_type == "DAILYSUMMARY":
                changed = self._save_daily_summary(text)
            else:
                if expires_in not in EXPIRATION_DURATIONS and expires_in not in ("NONE", "PERMANENT"):
                    print(f"[MemoryManager] Unknown MEMORY_EXPIRE: '{expires_in}' — treating as PERMANENT.")
                    expires_in = "PERMANENT"

                entry = {
                    "id": uuid.uuid4().hex[:8],
                    "text": text,
                    "created_at": datetime.now().isoformat(timespec="minutes"),
                    "expires_in": expires_in,
                }

                if entry_type == "FACT":
                    self.memory["facts"].append(entry)
                elif entry_type == "MEMORY":
                    self.memory["memories"].append(entry)

                self._save()
                changed = True

        if changed:
            self._notify()

    def _save_daily_summary(self, text):
        text = (text or "").strip()
        if not text or text == "NONE":
            return False

        now = datetime.now()
        today = now.strftime("%Y-%m-%d")

        existing = self.memory["daily_summaries"].get(today, {}).get("text", "").strip()

        if text in existing:
            return False

        combined = f"{existing} {text}".strip()

        if len(combined) > DAILY_SUMMARY_MAX_CHARS:
            combined = combined[-DAILY_SUMMARY_MAX_CHARS:]
            cut = combined.find(". ")
            if 0 <= cut < len(combined) - 1:
                combined = combined[cut + 2:]

        self.memory["daily_summaries"][today] = {
            "text": combined,
            "updated_at": now.isoformat(timespec="minutes"),
        }

        self._save()
        return True

    # ------------------------------------------------------------------
    # Browsing and editing (Memories page)
    # ------------------------------------------------------------------

    def counts(self):
        with self._lock:
            return {
                "memories": len(self.memory["memories"]),
                "facts": len(self.memory["facts"]),
                "daily_summaries": len(self.memory["daily_summaries"]),
            }

    def list_entries(self, category):
        """
        Newest first. Each entry is {"id", "text", "date"} — `date` is a
        datetime or None. For daily summaries the id is the date key.
        """
        if category not in CATEGORIES:
            return []

        with self._lock:
            if category == "daily_summaries":
                entries = []
                for key, value in self.memory["daily_summaries"].items():
                    try:
                        date = datetime.strptime(key, "%Y-%m-%d")
                    except ValueError:
                        date = None
                    entries.append({"id": key, "text": value.get("text", ""), "date": date})
            else:
                entries = [
                    {
                        "id": item["id"],
                        "text": item["text"],
                        "date": self._parse_created_at(item.get("created_at")),
                    }
                    for item in self.memory[category]
                ]

        entries.sort(key=lambda e: e["date"] or datetime.min, reverse=True)
        return entries

    def update_entry(self, category, entry_id, text):
        text = (text or "").strip()
        if category not in CATEGORIES or not text:
            return False

        with self._lock:
            if category == "daily_summaries":
                target = self.memory["daily_summaries"].get(entry_id)
                if target is None:
                    return False
                target["text"] = text
                target["updated_at"] = datetime.now().isoformat(timespec="minutes")
            else:
                target = next((i for i in self.memory[category] if i.get("id") == entry_id), None)
                if target is None:
                    return False
                target["text"] = text

            self._save()

        self._notify()
        return True

    def delete_entry(self, category, entry_id):
        if category not in CATEGORIES:
            return False

        with self._lock:
            if category == "daily_summaries":
                if entry_id not in self.memory["daily_summaries"]:
                    return False
                del self.memory["daily_summaries"][entry_id]
            else:
                remaining = [i for i in self.memory[category] if i.get("id") != entry_id]
                if len(remaining) == len(self.memory[category]):
                    return False
                self.memory[category] = remaining

            self._save()

        self._notify()
        return True

    # ------------------------------------------------------------------
    # Expiration
    # ------------------------------------------------------------------

    def clear_expired(self):
        with self._lock:
            now = datetime.now()
            removed_count = 0

            for category in ("facts", "memories"):
                remaining = []

                for item in self.memory.get(category, []):
                    expires_in = item.get("expires_in", "NONE")

                    if expires_in in ("NONE", "PERMANENT"):
                        remaining.append(item)
                        continue

                    duration = EXPIRATION_DURATIONS.get(expires_in)
                    created_at = self._parse_created_at(item.get("created_at"))

                    if duration is None or created_at is None:
                        remaining.append(item)
                        continue

                    if now - created_at >= duration:
                        removed_count += 1
                    else:
                        remaining.append(item)

                self.memory[category] = remaining

            cutoff = (now - DAILY_SUMMARY_RETENTION).date()
            for date_str in list(self.memory["daily_summaries"].keys()):
                try:
                    summary_date = datetime.strptime(date_str, "%Y-%m-%d").date()
                except ValueError:
                    continue

                if summary_date < cutoff:
                    del self.memory["daily_summaries"][date_str]
                    removed_count += 1

            if removed_count > 0:
                print(f"[MemoryManager] Removed {removed_count} expired memory entrie(s).")
                self._save()

        if removed_count > 0:
            self._notify()