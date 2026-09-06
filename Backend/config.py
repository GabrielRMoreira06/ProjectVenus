import os

from dotenv import load_dotenv

load_dotenv()

GEMINI_KEY = os.getenv("GEMINI_API_KEY")
ELEVEN_KEY = os.getenv("ELEVENLABS_API_KEY")

VOICE_ID_MAIN = "pKkhATTL1UmLW2xypBiO"

MODEL = "gemini-3.1-flash-lite"

TTS_MODEL = "eleven_v2"

VOICE_ID = "mSFXgMiywhuGsduQwaRf"