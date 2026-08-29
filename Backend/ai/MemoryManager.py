"""
memory_manager.py

Persists long-term information about the user across sessions: facts,
memories (dated events), and habits (patterns noticed across
memories). Each entry can optionally expire after a fixed duration;
entries with no expiration are kept forever.
"""

import json
from datetime import datetime, timedelta
from pathlib import Path

EXPIRATION_DURATIONS = {
    "6HOURS": timedelta(hours=6),
    "1DAY": timedelta(days=1),
    "1WEEK": timedelta(weeks=1),
    "1MONTH": timedelta(days=30),
}

VALID_TYPES = ("FACT", "MEMORY", "HABIT")


class MemoryManager:

    def __init__(self, file_path="memory.json"):
        self.file_path = Path(file_path)
        self.memory = self._load()

    def get_prompt(self):
        facts = "\n".join(f"- {item['text']}" for item in self.memory["facts"])
        memories = "\n".join(self._format_item(item) for item in self.memory["memories"])
        habits = "\n".join(self._format_item(item) for item in self.memory["habits"])

        return f"""
FACTS:
{facts}

MEMORIES (with date/time/day of week, so you can notice routine patterns):
{memories}

HABITS:
{habits}
"""

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

    def _load(self):
        if not self.file_path.exists():
            return {"facts": [], "memories": [], "habits": []}

        try:
            with open(self.file_path, "r", encoding="utf-8") as f:
                content = f.read().strip()

                if not content:
                    raise json.JSONDecodeError("empty file", content, 0)

                data = json.loads(content)

        except (json.JSONDecodeError, OSError):
            print(f"[MemoryManager] '{self.file_path}' is empty or corrupted — starting with empty memory.")
            data = {}

        data.setdefault("facts", [])
        data.setdefault("memories", [])
        data.setdefault("habits", [])

        return data

    def _save(self):
        with open(self.file_path, "w", encoding="utf-8") as f:
            json.dump(self.memory, f, ensure_ascii=False, indent=4)

    def save(self, entry_type, text, expires_in="NONE"):
        if entry_type not in VALID_TYPES:
            print(f"[MemoryManager] Unknown MEMORY_TYPE: '{entry_type}' — ignoring.")
            return

        if expires_in not in EXPIRATION_DURATIONS and expires_in not in ("NONE", "PERMANENT"):
            print(f"[MemoryManager] Unknown MEMORY_EXPIRE: '{expires_in}' — treating as PERMANENT.")
            expires_in = "PERMANENT"

        entry = {
            "text": text,
            "created_at": datetime.now().isoformat(timespec="minutes"),
            "expires_in": expires_in,
        }

        if entry_type == "FACT":
            self.memory["facts"].append(entry)
        elif entry_type == "MEMORY":
            self.memory["memories"].append(entry)
        elif entry_type == "HABIT":
            self.memory["habits"].append(entry)

        self._save()

    def clear_expired(self):
        """
        Removes entries whose lifetime (MEMORY_EXPIRE) has passed.
        PERMANENT and NONE never expire. Meant to be called
        periodically by a maintenance task.
        """
        now = datetime.now()
        removed_count = 0

        for category in ("facts", "memories", "habits"):
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