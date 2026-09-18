import os

from dotenv import load_dotenv

load_dotenv()

GEMINI_KEY = os.getenv("GEMINI_API_KEY")
MODEL = "gemini-3.1-flash-lite"
PIPER_MODEL_PATH = r"C:\Users\User\Documents\ProjectVenus\Backend\piper\en_GB-cori-medium.onnx"

EMAIL_ADDRESS = os.getenv("EMAIL_ADDRESS")
EMAIL_APP_PASSWORD = os.getenv("EMAIL_APP_PASSWORD")
EMAIL_IMAP_SERVER = os.getenv("EMAIL_IMAP_SERVER", "imap.gmail.com")