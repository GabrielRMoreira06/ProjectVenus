"""
InternetCheck.py

Registered as the INTERNETCHECK on-call action (see
on_call_actions/__init__.py).

Measures ping (TCP connect time), download and upload speed against
Cloudflare's speed endpoints and returns a short summary for Gemini.
Each measurement fails independently, so a broken upload test still
reports ping and download.
"""

import socket
import time

import requests

PING_HOST = ("1.1.1.1", 443)
PING_SAMPLES = 5
DOWNLOAD_URL = "https://speed.cloudflare.com/__down?bytes={}"
UPLOAD_URL = "https://speed.cloudflare.com/__up"
DOWNLOAD_BYTES = 20 * 1024 * 1024
UPLOAD_BYTES = 8 * 1024 * 1024
TIMEOUT = 30


def _measure_ping():
    samples = []

    for _ in range(PING_SAMPLES):
        start = time.perf_counter()
        with socket.create_connection(PING_HOST, timeout=5):
            pass
        samples.append((time.perf_counter() - start) * 1000)

    return sum(samples) / len(samples)


def _measure_download():
    start = time.perf_counter()
    received = 0

    with requests.get(DOWNLOAD_URL.format(DOWNLOAD_BYTES), stream=True, timeout=TIMEOUT) as response:
        response.raise_for_status()
        for chunk in response.iter_content(chunk_size=65536):
            received += len(chunk)

    elapsed = time.perf_counter() - start
    return received * 8 / elapsed / 1_000_000


def _measure_upload():
    payload = b"0" * UPLOAD_BYTES

    start = time.perf_counter()
    response = requests.post(UPLOAD_URL, data=payload, timeout=TIMEOUT)
    response.raise_for_status()
    elapsed = time.perf_counter() - start

    return UPLOAD_BYTES * 8 / elapsed / 1_000_000


def internet_check(result):
    parts = []

    try:
        parts.append(f"ping {_measure_ping():.0f} ms")
    except Exception:
        parts.append("ping failed")

    try:
        parts.append(f"download {_measure_download():.1f} Mbps")
    except Exception:
        parts.append("download failed")

    try:
        parts.append(f"upload {_measure_upload():.1f} Mbps")
    except Exception:
        parts.append("upload failed")

    if all("failed" in part for part in parts):
        return "Internet check failed on every test, the connection may be down."

    return "[SYSTEM MESSAGE: Internet check: " + ", ".join(parts) + ".]"
