"""
EmailMonitor.py

Polls the configured inbox via IMAP for unseen emails since the last
check, and hands their content to Gemini as a system message — same
pipeline shape as every other monitor (internal cooldown -> builder ->
Orchestrator -> GeminiWorker). Notify-only for now: Venus can comment
on an email, nothing more. No auto-reply, no sending, no marking
anything other than what IMAP itself marks as read on fetch.

Multiple unseen emails found in one check are batched into a single
Gemini call (one summary block, one response) rather than firing once
per email — avoids spamming several responses back-to-back through
Orchestrator for something that arrived in one poll window.

Requires EMAIL_ADDRESS / EMAIL_APP_PASSWORD / EMAIL_IMAP_SERVER in
config.py (an app password, not your real password — for Gmail:
Google Account -> Security -> App Passwords, with 2FA on).
"""

import email
import imaplib
from email.header import decode_header

from ai.GeminiWorker import worker
from Orchestrator import Category
from Monitors.BaseMonitor import BaseMonitor
from config import EMAIL_ADDRESS, EMAIL_APP_PASSWORD, EMAIL_IMAP_SERVER

MAX_EMAILS_PER_CHECK = 5
MAX_BODY_CHARS = 1000


class EmailMonitor(BaseMonitor):

    def __init__(self, orchestrator, interval=3000):
        super().__init__(orchestrator, interval)

    def check(self):
        emails = self._fetch_unseen()

        if not emails:
            return

        self._fire(emails)

    def _fetch_unseen(self):
        if not EMAIL_ADDRESS or not EMAIL_APP_PASSWORD:
            print("[EmailMonitor] EMAIL_ADDRESS/EMAIL_APP_PASSWORD not set in config.py — skipping.")
            return []

        try:
            connection = imaplib.IMAP4_SSL(EMAIL_IMAP_SERVER)
            connection.login(EMAIL_ADDRESS, EMAIL_APP_PASSWORD)
            connection.select("INBOX")

            status, data = connection.search(None, "UNSEEN")
            if status != "OK" or not data or not data[0]:
                connection.logout()
                return []

            uids = data[0].split()[:MAX_EMAILS_PER_CHECK]
            emails = []

            for uid in uids:
                status, msg_data = connection.fetch(uid, "(RFC822)")
                if status != "OK" or not msg_data or msg_data[0] is None:
                    continue

                message = email.message_from_bytes(msg_data[0][1])
                emails.append(self._parse_message(message))

            connection.logout()
            return emails

        except Exception as e:
            print(f"[EmailMonitor] Failed to check inbox: {e}")
            return []

    def _parse_message(self, message):
        return {
            "subject": self._decode(message.get("Subject", "(no subject)")),
            "sender": self._decode(message.get("From", "(unknown sender)")),
            "body": self._extract_body(message),
        }

    def _decode(self, value):
        if not value:
            return ""

        decoded, encoding = decode_header(value)[0]
        if isinstance(decoded, bytes):
            return decoded.decode(encoding or "utf-8", errors="ignore")
        return decoded

    def _extract_body(self, message):
        if message.is_multipart():
            for part in message.walk():
                if part.get_content_type() == "text/plain" and not part.get("Content-Disposition"):
                    charset = part.get_content_charset() or "utf-8"
                    try:
                        return part.get_payload(decode=True).decode(charset, errors="ignore")[:MAX_BODY_CHARS]
                    except Exception:
                        continue
            return "(no plain text body found)"

        charset = message.get_content_charset() or "utf-8"
        try:
            return message.get_payload(decode=True).decode(charset, errors="ignore")[:MAX_BODY_CHARS]
        except Exception:
            return "(failed to decode body)"

    def _fire(self, emails):
        print(f"[EmailMonitor] {len(emails)} new email(s), alerting.")

        summary = "\n\n".join(
            f"From: {e['sender']}\nSubject: {e['subject']}\nBody: {e['body']}"
            for e in emails
        )

        def builder():
            return worker.run(
                user_text=f"[SYSTEM MESSAGE: {len(emails)} new email(s) arrived in the inbox.]\n\n{summary}"
            )

        self.orchestrator.add(Category.MONITOR, builder)