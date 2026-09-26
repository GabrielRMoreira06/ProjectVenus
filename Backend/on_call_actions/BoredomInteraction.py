"""
BoredomInteraction.py

Fires the boredom escalation: comments on a random image from the
user's Downloads folder via a Gemini call restricted to SHOWIMAGE,
then forces action/image_path afterward — SHOWIMAGE's normal path
resolves an IMAGE_QUERY through internet search, but the whole point
here is reacting to something already sitting on the user's disk, so
that resolution is bypassed and the local file is injected directly.

Same reasoning as on_call_actions/LowerBrightnessVolume.py for living
outside MoodController: keeps the controller focused on tracking/
thresholding mood values, not owning every side effect a threshold
triggers. `orchestrator`/`worker`/`MoodVariant` are looked up lazily,
inside fire() (not at module load time) — ai.GeminiWorker imports
ai.MoodController, and Server.py constructs `orchestrator` after this
module is first imported (same sys.modules["__main__"] pattern used
throughout — Reminder.py, EXPManager.py, MoodController's own
anger/energy escalations).
"""

import random
from pathlib import Path

from PIL import Image

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
DOWNLOADS_FOLDER = Path.home() / "Downloads"


def _pick_random_image_from_disk():
    if not DOWNLOADS_FOLDER.is_dir():
        return None

    candidates = [
        path for path in DOWNLOADS_FOLDER.iterdir()
        if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS
    ]

    if not candidates:
        return None

    return random.choice(candidates)


def fire(mood):
    """
    mood: the MoodController instance to reset once this fires (and to
    release the rearm guard on either way). Takes it explicitly rather
    than importing the shared `mood` singleton here, since the caller
    (MoodController._check_boredom_threshold) already has `self`.
    """
    import sys
    orchestrator = sys.modules["__main__"].orchestrator

    from Orchestrator import Category
    from ai.GeminiWorker import worker
    from ai.MoodController import MoodVariant

    image_path = _pick_random_image_from_disk()

    if not image_path:
        print("[BoredomInteraction] No image found in the Downloads folder — skipping.")
        mood._boredom_alert_firing = False
        return

    print(f"[BoredomInteraction] Boredom at {mood.boredom}, commenting on: {image_path}")

    def builder():
        try:
            image = Image.open(image_path)
            result = worker.run(
                user_text="""
                [SYSTEM MESSAGE: you are too bored. Pick your evil action.
                SHOWIMAGE: comment on this image you found on the user's downloads]
                """,
                image=image,
                allowed_actions={"SHOWIMAGE"},
            )

            result["action"] = "SHOWIMAGE"
            result["image_path"] = str(image_path)

            mood.adjust(MoodVariant.BOREDOM, 50 - mood.boredom)

            return result
        finally:
            mood._boredom_alert_firing = False

    orchestrator.add(Category.MONITOR, builder)