import os

from dotenv import load_dotenv

load_dotenv()

GEMINI_KEY = os.getenv("GEMINI_API_KEY")
ELEVEN_KEY = os.getenv("ELEVENLABS_API_KEY")

VOICE_ID_MAIN = "pKkhATTL1UmLW2xypBiO"

MODEL = "gemini-3.5-flash"

TTS_MODEL = "eleven_v3"

VOICE_ID = "bd1tT0za4YJgNIVIjEeZ"