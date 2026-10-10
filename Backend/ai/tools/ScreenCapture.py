"""
screen_capture.py

Captures the primary monitor and returns a thumbnail-sized PIL Image,
ready to send to Gemini as multimodal input.
"""

import mss
from PIL import Image


def capture_screen():
    with mss.mss() as sct:
        monitor = sct.monitors[1]
        raw = sct.grab(monitor)

        image = Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")
        image.thumbnail((1280, 720))

        return image