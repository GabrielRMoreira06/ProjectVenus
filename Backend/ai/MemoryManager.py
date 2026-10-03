"""
memory_manager.py

Persists long-term information about the user across sessions: facts,
memories (dated events), and daily summaries (one per calendar day,
overwritten on every update). FACT/MEMORY entries get an auto-generated
id and can optionally expire; entries with no expiration are kept forever.
"""

import json
import os
import shutil
import threading
import uuid
from datetime import datetime, timedelta
from pathlib import Path

from config import DATA_DIR

EXPIRATION_DURATIONS = {
    "6HOURS": timedelta(hours=6),
    "1DAY": timedelta(days=1),
    "1WEEK": timedelta(weeks=1),
    "1MONTH": timedelta(days=30),
}

VALID_TYPES = ("FACT", "MEMORY", "DAILYSUMMARY")

DAILY_SUMMARIES_IN_PROMPT = 7  # today + previous 6 days


class MemoryManager:

    def __init__(self, file_path="memory.json"):
        path = Path(file_path)
        self.file_path = path if path.is_absolute() else DATA_DIR / path
        self.backup_path = self.file_path.with_name(self.file_path.name + ".bak")
        self._lock = threading.RLock()
        self.memory = self._load()
        print(f"[MemoryManager] Using '{self.file_path}'.")

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

DAILY SUMMARIES (most recent days, today's first; sending DAILYSUMMARY overwrites today's entry, so include everything worth keeping from it):
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

    def _read_json(self, path):
        if not path.exists():
            return None

        try:
            content = path.read_text(encoding="utf-8").strip()
            if not content:
                return None
            data = json.loads(content)
            return data if isinstance(data, dict) else None
        except (json.JSONDecodeError, OSError):
            return None

    def _load(self):
        data = self._read_json(self.file_path)

        if data is None and self.file_path.exists():
            print(f"[MemoryManager] '{self.file_path}' is empty or corrupted.")

            corrupt_path = self.file_path.with_name(self.file_path.name + ".corrupt")
            try:
                shutil.copy2(self.file_path, corrupt_path)
            except OSError:
                pass

            data = self._read_json(self.backup_path)
            if data is not None:
                print(f"[MemoryManager] Recovered from '{self.backup_path}'.")

        if data is None:
            data = {}

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

        if self._read_json(self.file_path) is not None:
            try:
                shutil.copy2(self.file_path, self.backup_path)
            except OSError:
                pass

        os.replace(temp_path, self.file_path)

    def save(self, entry_type, text, expires_in="NONE"):
        if entry_type not in VALID_TYPES:
            print(f"[MemoryManager] Unknown MEMORY_TYPE: '{entry_type}' — ignoring.")
            return

        if not text or text.strip().upper() == "NONE":
            print(f"[MemoryManager] Empty MEMORY_TEXT for {entry_type} — ignoring.")
            return

        with self._lock:
            if entry_type == "DAILYSUMMARY":
                self._save_daily_summary(text)
                return

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

    def _save_daily_summary(self, text):
        now = datetime.now()
        today = now.strftime("%Y-%m-%d")

        self.memory["daily_summaries"][today] = {
            "text": text,
            "updated_at": now.isoformat(timespec="minutes"),
        }

        self._save()

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

            if removed_count > 0:
                print(f"[MemoryManager] Removed {removed_count} expired memory entrie(s).")
                self._save()