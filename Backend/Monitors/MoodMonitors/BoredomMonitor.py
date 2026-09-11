"""
boredom_monitor.py

Watches boredom. When it's low enough, Venus comments on a random
image from the user's Downloads folder.

KNOWN GAP: this monitor forces action="OPENIMAGE" with a path to a
LOCAL file, but the current /response pipeline (server.py) only
delivers text/action/mood fields — there's no image-serving endpoint
yet (the old /imagem/<id> route + static file registry hasn't been
rebuilt in this rewrite). Until that exists, an OPENIMAGE response from
this monitor will reach Unity, but ImageHolder will have nothing to
actually fetch. Left in place — with image_path attached — so wiring
up real delivery later is a small addition here, not a rewrite.
"""

import random
from pathlib import Path
from PIL import Image

from ai.MoodController import mood
from ai.GeminiWorker import worker
from Orchestrator import Category
from Monitors.BaseMonitor import BaseMonitor

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
DOWNLOADS_FOLDER = Path.home() / "Downloads"


def pick_random_image_from_disk():
    """
    Picks a random image file directly inside the Downloads folder
    (does not look into subfolders).
    """
    if not DOWNLOADS_FOLDER.is_dir():
        return None

    candidates = [
        path for path in DOWNLOADS_FOLDER.iterdir()
        if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS
    ]

    if not candidates:
        return None

    return random.choice(candidates)


class BoredomMonitor(BaseMonitor):

    def __init__(self, orchestrator, interval=3000, boredom_limit=70):
        super().__init__(orchestrator, interval)
        self.boredom_limit = boredom_limit

    def check(self):
        if mood.boredom < self.boredom_limit:
            return

        self._fire()

    def _fire(self):
        image_path = pick_random_image_from_disk()

        if not image_path:
            print("[BoredomMonitor] No image found in the Downloads folder.")
            return

        print(f"[BoredomMonitor] Boredom low ({mood.boredom}), commenting on: {image_path}")

        def builder():
            image = Image.open(image_path)
            result = worker.run(
                user_text="[SYSTEM MESSAGE: you found this image on the user's downloads.]",
                image=image,
            )
            result["action"] = "OPENIMAGE"       # forced, not decided by Gemini
            result["image_path"] = str(image_path)  # see module docstring — not yet served to Unity
            return result

        self.orchestrator.add(Category.MONITOR, builder)