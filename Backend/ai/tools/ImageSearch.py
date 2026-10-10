"""
image_search.py

Searches for an image matching a text description and downloads it
locally. Used whenever a response's action is SHOWIMAGE and Gemini
provided an IMAGE_QUERY (see GeminiWorker._resolve_image) — the local
file is later served to Unity through the /image/<id> endpoint in
server.py.
"""

import tempfile

import requests
from ddgs import DDGS

EXTENSION_BY_CONTENT_TYPE = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/gif": ".gif",
    "image/webp": ".webp",
}


def search_image(query, max_results=5):
    """
    Searches for an image matching `query` and saves it to a temporary
    file. Returns the path to the downloaded file, or None if no image
    could be found or downloaded.
    """
    with DDGS() as ddgs:
        results = list(ddgs.images(f"site:x.com {query}", max_results=max_results))

    if not results:
        return None

    for result in results:
        image_url = result["image"]

        try:
            response = requests.get(image_url, timeout=10)
            response.raise_for_status()

            content_type = response.headers.get("Content-Type", "").split(";")[0]
            extension = EXTENSION_BY_CONTENT_TYPE.get(content_type, ".jpg")

            temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=extension)
            temp_file.write(response.content)
            temp_file.close()

            return temp_file.name

        except Exception:
            continue

    return None