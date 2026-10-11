import os

from dotenv import load_dotenv
from pathlib import Path
import shutil

load_dotenv()


GEMINI_KEY = os.getenv("GEMINI_API_KEY")
MODEL = "gemini-3.6-flash-lite"
PIPER_MODEL_PATH = r"C:\Users\User\Documents\ProjectVenus\Backend\piper\en_GB-cori-medium.onnx"

EMAIL_ADDRESS = os.getenv("EMAIL_ADDRESS")
EMAIL_APP_PASSWORD = os.getenv("EMAIL_APP_PASSWORD")
EMAIL_IMAP_SERVER = os.getenv("EMAIL_IMAP_SERVER", "imap.gmail.com")

WALLPAPER_VIDEOS = ["C:/Users/User/Downloads/mephisto.mp4"]




DATA_DIR = Path(__file__).resolve().parent
STATE_DIR = DATA_DIR / "data"
STATE_DIR.mkdir(exist_ok=True)
NOTEPAD_PATH = STATE_DIR / "notepad_autosave.txt"

# One-time migration of old state files into STATE_DIR
for _name in ("mood_state.json", "exp_state.json", "boot_state.json",
              "preferences.json", "persistent_reminders.json",
              "hardware_state.json", "notepad_autosave.txt",
              "memory.json", "wallpapers.json"):
    _new = STATE_DIR / _name
    for _old in (DATA_DIR / _name, Path.cwd() / _name):
        if _old.is_file() and not _new.exists():
            shutil.move(str(_old), str(_new))
            break