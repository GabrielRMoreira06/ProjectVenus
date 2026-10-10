"""
PdfSummarizer.py

Extracts text from a PDF and summarizes it via a single, separate
Gemini call — deliberately NOT sent through GeminiWorker's ongoing
chat session (worker.chat). That session's history is resent on every
future turn, so dumping a full PDF's text into it would inflate every
subsequent request for the rest of the session. This makes its own
one-off call instead; the caller should feed only the resulting short
summary into worker.chat as a system message, same pattern as
FindFile.py's outcome or HardwareInspect's prompt.

Text-only: no OCR, no page rasterization. A scanned/image-only PDF
will simply produce little or no extractable text.

Requires: pip install pypdf
"""

from pathlib import Path

from google import genai
from pypdf import PdfReader

from config import GEMINI_KEY

MODEL_NAME = "gemini-3.1-flash-lite"
MAX_CHARS = 30000  # rough cap on extracted text sent to Gemini

SUMMARY_PROMPT = (
    "Summarize the following PDF content in 3-6 sentences. "
    "Focus on the main points only, no preamble, no markdown.\n\n"
    "PDF CONTENT:\n{content}"
)


class PdfSummarizer:

    def __init__(self, model_name=MODEL_NAME):
        self.model_name = model_name
        self._client = None

    def _get_client(self):
        if self._client is None:
            self._client = genai.Client(api_key=GEMINI_KEY)
        return self._client

    def _extract_text(self, path):
        reader = PdfReader(str(path))
        pages = []

        for page in reader.pages:
            try:
                pages.append(page.extract_text() or "")
            except Exception:
                continue

        return "\n".join(pages).strip()

    def summarize(self, path):
        """
        Returns a short text summary of the PDF at `path`, or None if
        no text could be extracted. Never touches worker.chat — this
        call has no memory of anything else going on with Venus.
        """
        path = Path(path)

        if not path.exists():
            print(f"[PdfSummarizer] File not found: {path}")
            return None

        text = self._extract_text(path)

        if not text:
            print(f"[PdfSummarizer] No extractable text in: {path}")
            return None

        truncated = text[:MAX_CHARS]

        try:
            response = self._get_client().models.generate_content(
                model=self.model_name,
                contents=SUMMARY_PROMPT.format(content=truncated),
            )
            return response.text.strip()

        except Exception as error:
            print(f"[PdfSummarizer] Failed to summarize '{path}': {error}")
            return None


# Shared instance, same pattern as `worker`/`mood`/`exp_manager` elsewhere.
pdf_summarizer = PdfSummarizer()