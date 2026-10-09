"""
WallpaperStore.py

Persistent wallpaper library. Imported videos are COPIED into
Backend/wallpapers/ and only the copy is ever referenced, so deleting
the original file doesn't break anything. wallpapers.json stores just
the copied filenames. Cached thumbnails live in wallpapers/thumbs/.
Same load-once / rewrite-on-change pattern as Preferences/MoodController.
"""

import json
import os
import shutil
from pathlib import Path

from config import DATA_DIR

WALLPAPER_DIR = DATA_DIR / "wallpapers"
THUMB_DIR = WALLPAPER_DIR / "thumbs"


class WallpaperStore:

    def __init__(self, file_path="wallpapers.json"):
        path = Path(file_path)
        self.file_path = path if path.is_absolute() else DATA_DIR / path
        THUMB_DIR.mkdir(parents=True, exist_ok=True)

        self._listeners = []
        self.videos = self._load()

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _load(self):
        if not self.file_path.exists():
            return []

        try:
            with open(self.file_path, "r", encoding="utf-8") as f:
                content = f.read().strip()
                data = json.loads(content) if content else {}
                entries = [v for v in data.get("videos", []) if isinstance(v, str)]
        except (json.JSONDecodeError, OSError, AttributeError):
            print(f"[WallpaperStore] '{self.file_path}' is empty or corrupted — starting with an empty list.")
            return []

        videos = []
        changed = False

        for entry in entries:
            name = entry

            # Old format: an absolute path to the original file. Copy it
            # into the library now, if it still exists.
            if os.path.isabs(entry):
                changed = True

                if Path(entry).parent == WALLPAPER_DIR:
                    name = Path(entry).name
                elif os.path.isfile(entry):
                    try:
                        name = self.copy_into_library(entry)
                        print(f"[WallpaperStore] Migrated '{entry}' into the library.")
                    except OSError as error:
                        print(f"[WallpaperStore] Failed to migrate '{entry}': {error}")
                        continue
                else:
                    print(f"[WallpaperStore] Dropping '{entry}' — original no longer exists.")
                    continue

            if (WALLPAPER_DIR / name).is_file() and name not in videos:
                videos.append(name)
            else:
                changed = True

        if changed:
            self.videos = videos
            self._save()

        return videos

    def _save(self):
        with open(self.file_path, "w", encoding="utf-8") as f:
            json.dump({"videos": self.videos}, f, ensure_ascii=False, indent=4)

    # ------------------------------------------------------------------
    # Listeners
    # ------------------------------------------------------------------

    def subscribe(self, listener):
        """listener() is called after any change to the list."""
        self._listeners.append(listener)

    def _notify(self):
        for listener in self._listeners:
            listener()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_all(self):
        """Absolute paths to the library copies."""
        return [str(WALLPAPER_DIR / name) for name in self.videos]

    def thumbnail_path(self, video_path):
        return THUMB_DIR / f"{Path(video_path).stem}.jpg"

    def copy_into_library(self, source):
        """
        Copies `source` into the library and returns the copy's
        filename. Touches no list state and notifies nobody, so it's
        safe to call from a background thread (copies can be large).
        A same-name, same-size file is treated as already imported.
        """
        source = Path(source)
        WALLPAPER_DIR.mkdir(parents=True, exist_ok=True)

        dest = WALLPAPER_DIR / source.name

        if dest.exists():
            if dest.stat().st_size == source.stat().st_size:
                return dest.name

            counter = 1
            while dest.exists():
                dest = WALLPAPER_DIR / f"{source.stem}_{counter}{source.suffix}"
                counter += 1

        shutil.copy2(source, dest)
        return dest.name

    def add(self, name):
        """Registers a filename already copied into the library. Main thread only."""
        if name in self.videos:
            return

        self.videos.append(name)
        self._save()
        self._notify()

    def remove(self, path):
        name = Path(path).name

        if name not in self.videos:
            return

        self.videos.remove(name)
        self._save()

        for file in (WALLPAPER_DIR / name, self.thumbnail_path(path)):
            try:
                file.unlink()
            except OSError:
                pass  # e.g. still locked by mpv while it's the active wallpaper

        self._notify()


# Shared instance, same pattern as `preferences`/`mood` elsewhere.
wallpaper_store = WallpaperStore()